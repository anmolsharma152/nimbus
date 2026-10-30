import io
import os
import re
import shutil
import signal
import tarfile
import tempfile
import asyncio
import logging
import subprocess
import threading
import time
from typing import Optional, Tuple
import shlex
import base64
from .github_client import parse_github_repo
from .settings import settings

try:
    import docker
    from docker.models.containers import Container
    DOCKER_LIB_INSTALLED = True
except ImportError:
    DOCKER_LIB_INSTALLED = False

logger = logging.getLogger(__name__)

MANAGED_LABEL = "nimbus.managed"
# Unprivileged user baked into backend/Dockerfile.workspace
WORKSPACE_USER = "10001:10001"
# Subprocess mode: per-task UIDs (no passwd entry needed) far above normal user/system ranges
SANDBOX_UID_BASE = 200_000
SANDBOX_UID_RANGE = 100_000

# One Docker client (and its HTTP connection pool) shared by every workspace in the process
_docker_client = None
_docker_client_lock = threading.Lock()


def get_docker_client():
    """Returns the shared Docker client if the daemon answers a ping, else None (replacing dead clients)."""
    global _docker_client
    if not DOCKER_LIB_INSTALLED:
        return None
    with _docker_client_lock:
        if _docker_client is not None:
            try:
                _docker_client.ping()
                return _docker_client
            except Exception as e:
                logger.warning("Cached Docker client failed ping, reconnecting: %s", e)
                _close_quietly(_docker_client)
                _docker_client = None

        client = None
        try:
            client = docker.from_env()
            client.ping()
        except Exception as e:
            logger.info("Docker daemon unavailable, using subprocess workspace: %s", e)
            if client is not None:
                _close_quietly(client)
            return None
        _docker_client = client
        return client


def _close_quietly(client):
    try:
        client.close()
    except Exception:
        pass


def reap_orphaned_containers(client, max_age_seconds: float) -> int:
    """Force-removes Nimbus containers older than max_age_seconds (left behind by crashed workers)."""
    removed = 0
    now = time.time()
    for container in client.containers.list(all=True, filters={"label": f"{MANAGED_LABEL}=true"}):
        try:
            created = int(container.labels.get("nimbus.created", "0"))
        except ValueError:
            created = 0
        if now - created < max_age_seconds:
            continue
        try:
            container.remove(force=True)
            removed += 1
        except Exception as e:
            logger.warning("Failed to reap container %s: %s", getattr(container, "name", "?"), e)
    return removed


def reap_orphaned_volumes(client, max_age_seconds: float) -> int:
    """Removes Nimbus repo volumes older than max_age_seconds whose containers are gone."""
    removed = 0
    now = time.time()
    for volume in client.volumes.list(filters={"label": f"{MANAGED_LABEL}=true"}):
        labels = (getattr(volume, "attrs", None) or {}).get("Labels") or {}
        try:
            created = int(labels.get("nimbus.created", "0"))
        except ValueError:
            created = 0
        if now - created < max_age_seconds:
            continue
        try:
            volume.remove(force=True)
            removed += 1
        except Exception as e:
            logger.warning("Failed to reap volume %s: %s", getattr(volume, "name", "?"), e)
    return removed


# --- Token-safe git operations ---
#
# The agent controls everything inside its workspace, including the repo's .git directory
# (hooks, `url.*.insteadOf`, `core.fsmonitor`, ...). Commands that hold the GitHub token therefore
# never run as the agent's user and never touch the agent's .git: clone happens before the agent
# starts, and push replays the agent's patch onto a fresh private clone.

GITHUB_HTTPS_PREFIX = "https://github.com/"
SANDBOX_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def git_auth_env(github_token: Optional[str]) -> dict:
    """Git config passed via GIT_CONFIG_* env vars, so the token never appears in a process cmdline.

    The auth header is scoped to https://github.com/ so it is never sent to any other host.
    """
    entries = [("core.hooksPath", "/dev/null")]
    if github_token:
        header = base64.b64encode(f"x-access-token:{github_token}".encode()).decode()
        entries.append((f"http.{GITHUB_HTTPS_PREFIX}.extraheader", f"AUTHORIZATION: basic {header}"))
    env = {"GIT_CONFIG_COUNT": str(len(entries)), "GIT_TERMINAL_PROMPT": "0"}
    for i, (key, value) in enumerate(entries):
        env[f"GIT_CONFIG_KEY_{i}"] = key
        env[f"GIT_CONFIG_VALUE_{i}"] = value
    return env


def resolve_clone_url(repo_url: str, github_token: Optional[str]) -> str:
    cleaned_url = repo_url.strip()
    parsed = parse_github_repo(cleaned_url)
    if github_token and parsed:
        owner, repo = parsed
        return f"{GITHUB_HTTPS_PREFIX}{owner}/{repo}.git"
    return cleaned_url


def clone_script(clone_url: str, dest: str) -> str:
    """Clones and prints the base commit SHA (nothing for an empty repository)."""
    return (
        f"git clone -- {shlex.quote(clone_url)} {shlex.quote(dest)} && "
        f"(git -C {shlex.quote(dest)} rev-parse HEAD 2>/dev/null || true)"
    )


def parse_base_sha(output: str) -> Optional[str]:
    for line in reversed(output.splitlines()):
        if _SHA_RE.match(line.strip()):
            return line.strip()
    return None


def patch_script(base_sha: str) -> str:
    """Run inside the agent workspace: every change since the base commit, binary-safe."""
    return f"git add -A && git diff --cached --binary {shlex.quote(base_sha)}"


def push_script(
    remote_url: str,
    base_sha: str,
    branch_name: str,
    patch_path: str,
    workdir: str,
    message: str,
    author_name: str,
    author_email: str
) -> str:
    q = shlex.quote
    return "\n".join([
        "set -e",
        f"git init -q {q(workdir)}",
        f"cd {q(workdir)}",
        f"git remote add origin {q(remote_url)}",
        f"git fetch -q --depth 1 origin {q(base_sha)}",
        f"git checkout -q -b {q(branch_name)} FETCH_HEAD",
        f"git apply --index {q(patch_path)}",
        f"git -c user.name={q(author_name)} -c user.email={q(author_email)} commit -q -m {q(message)}",
        f"git push -q origin {q(branch_name)}",
    ])


def github_push_url(repo_url: str) -> Optional[str]:
    parsed = parse_github_repo(repo_url)
    if not parsed:
        return None
    owner, repo = parsed
    return f"{GITHUB_HTTPS_PREFIX}{owner}/{repo}.git"


def clean_commit_message(message: str) -> str:
    return message.replace("'", "").replace("\n", " ").strip()[:100]


def _tar_bytes(files: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class DockerWorkspace:
    """Manages an ephemeral Docker container for agent tasks when Docker daemon is reachable.

    The agent container runs as an unprivileged user from WORKSPACE_IMAGE (backend/Dockerfile.workspace)
    with the repo on a per-task volume. Git operations that need the GitHub token run in short-lived
    helper containers, so the token never enters the agent's container.
    """

    REPO_DIR = "/workspace/repo"

    def __init__(self, task_id: int, image: Optional[str] = None, client=None):
        self.task_id = task_id
        self.image = image or settings.WORKSPACE_IMAGE
        self.client = client or get_docker_client() or docker.from_env()
        self.container: Optional[Container] = None
        self.volume_name: Optional[str] = None
        self.base_sha: Optional[str] = None
        self.workdir: str = self.REPO_DIR

    def _labels(self) -> dict:
        return {
            MANAGED_LABEL: "true",
            "nimbus.task_id": str(self.task_id),
            "nimbus.created": str(int(time.time())),
        }

    def _sandbox_kwargs(self) -> dict:
        """Isolation settings shared by the agent container and git helper containers."""
        return dict(
            user=WORKSPACE_USER,
            mem_limit="1g",
            nano_cpus=2_000_000_000,
            pids_limit=256,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            labels=self._labels(),
        )

    def _ensure_image(self) -> Optional[str]:
        try:
            self.client.images.get(self.image)
            return None
        except docker.errors.ImageNotFound:
            pass
        try:
            logger.info("Pulling workspace image %s", self.image)
            self.client.images.pull(self.image)
            return None
        except Exception as e:
            return (
                f"Workspace image '{self.image}' is not available ({e}). Build it with: "
                "docker build -f backend/Dockerfile.workspace -t nimbus-workspace backend"
            )

    def _run_helper(
        self,
        script: str,
        environment: dict,
        mount_repo_volume: bool,
        files: Optional[dict] = None,
        timeout: int = 300
    ) -> Tuple[int, str]:
        """Runs a one-shot helper container (as the unprivileged user) and always removes it."""
        helper = self.client.containers.create(
            self.image,
            command=["bash", "-c", script],
            environment=environment,
            working_dir="/tmp",
            volumes={self.volume_name: {"bind": "/workspace", "mode": "rw"}} if mount_repo_volume else None,
            **self._sandbox_kwargs()
        )
        try:
            if files:
                helper.put_archive("/tmp", _tar_bytes(files))
            helper.start()
            try:
                status_code = helper.wait(timeout=timeout).get("StatusCode", 1)
            except Exception:
                return 124, f"[Git helper timed out after {timeout} seconds]"
            output = helper.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
            return status_code, output.strip()
        finally:
            try:
                helper.remove(force=True)
            except Exception as e:
                logger.warning("Failed to remove git helper container for task %s: %s", self.task_id, e)

    def setup(
        self,
        repo_url: Optional[str] = None,
        branch_name: Optional[str] = None,
        github_token: Optional[str] = None
    ) -> Tuple[int, str]:
        image_error = self._ensure_image()
        if image_error:
            return 1, image_error

        volume = self.client.volumes.create(
            name=f"nimbus-task-{self.task_id}-{int(time.time())}", labels=self._labels()
        )
        self.volume_name = volume.name

        logs = []
        if repo_url:
            cleaned_url = repo_url.strip()
            code, out = self._run_helper(
                clone_script(resolve_clone_url(cleaned_url, github_token), self.REPO_DIR),
                environment=git_auth_env(github_token),
                mount_repo_volume=True
            )
            if code != 0:
                return code, f"Failed to clone repository {cleaned_url}: {out}"
            self.base_sha = parse_base_sha(out)
            logs.append(f"Cloned {cleaned_url}")

        # The agent container starts only after every token-bearing process has exited
        self.container = self.client.containers.run(
            self.image,
            command="tail -f /dev/null",
            detach=True,
            name=f"nimbus-task-{self.task_id}-{int(time.time())}",
            working_dir="/workspace",
            volumes={self.volume_name: {"bind": "/workspace", "mode": "rw"}},
            **self._sandbox_kwargs()
        )

        if repo_url:

            if branch_name:
                code_b, out_b = self.execute_command(
                    f"git checkout -b {shlex.quote(branch_name)}",
                    workdir="/workspace/repo"
                )
                if code_b != 0:
                    return code_b, f"Failed to create branch {branch_name}: {out_b}"
                logs.append(f"Created branch {branch_name}")
            self.workdir = self.REPO_DIR
        else:
            init_repo = (
                "mkdir -p /workspace/repo && "
                "cd /workspace/repo && "
                "git init && "
                "echo '# Nimbus Task Workspace' > README.md && "
                "git add . && "
                "git commit -m 'Initial workspace commit'"
            )
            if branch_name:
                init_repo += f" && git checkout -b {shlex.quote(branch_name)}"
            code_init, out_init = self.execute_command(init_repo, workdir="/workspace")
            if code_init != 0:
                return code_init, f"Failed to initialize empty repository: {out_init}"
            self.workdir = self.REPO_DIR

        return 0, "\n".join(logs)

    def _exec_stdout(self, command: str, timeout: int = 300) -> Tuple[int, bytes]:
        """Like execute_command but returns raw stdout bytes (needed for binary patches)."""
        exec_result = self.container.exec_run(
            cmd=["bash", "-c", f"timeout {timeout} bash -c {shlex.quote(command)}"],
            workdir=self.workdir,
            demux=True
        )
        return exec_result.exit_code, exec_result.output[0] or b""

    def execute_command(self, command: str, workdir: Optional[str] = None, timeout: int = 300) -> Tuple[int, str]:
        if not self.container:
            raise RuntimeError("Workspace is not set up.")
        
        target_dir = workdir or self.workdir
        wrapped_cmd = f"timeout {timeout} bash -c {shlex.quote(command)}"
        bash_cmd = ["bash", "-c", wrapped_cmd]
        
        exec_result = self.container.exec_run(
            cmd=bash_cmd,
            workdir=target_dir,
            demux=True
        )
        
        exit_code = exec_result.exit_code
        stdout = exec_result.output[0] or b""
        stderr = exec_result.output[1] or b""
        
        output = stdout.decode('utf-8', errors='replace') + stderr.decode('utf-8', errors='replace')
        if exit_code == 124:
            output += f"\n[Command timed out after {timeout} seconds]"
        return exit_code, output.strip()

    def get_diff(self) -> str:
        if not self.container:
            return ""
        self.execute_command("git add -N .", workdir=self.workdir)
        code, out = self.execute_command("git diff HEAD", workdir=self.workdir)
        if not out.strip():
            code, out = self.execute_command("git diff", workdir=self.workdir)
        return out.strip()

    def get_file_base64(self, file_path: str) -> Optional[str]:
        """Reads a binary file inside container and returns its base64 encoded string."""
        if not self.container:
            return None
        code, out = self.execute_command(f"base64 -w 0 {shlex.quote(file_path)}", workdir=self.workdir)
        if code == 0 and out.strip():
            return out.strip()
        return None

    def commit_changes(self, message: str = "Nimbus agent automated changes") -> Tuple[int, str]:
        clean_msg = message.replace("'", "").replace("\n", " ").strip()[:100]
        return self.execute_command(
            f"git add -A && git commit -m {shlex.quote(clean_msg)} || true",
            workdir=self.workdir
        )

    def push_branch(
        self,
        branch_name: str,
        repo_url: str,
        github_token: Optional[str] = None,
        message: str = "Nimbus agent automated changes",
        author_name: str = "Nimbus Agent",
        author_email: str = "agent@nimbus.ai"
    ) -> Tuple[int, str]:
        """Replays the agent's changes onto a fresh clone inside a helper container and pushes it."""
        if not github_token:
            return 1, "No GitHub token available to push branch."
        remote_url = github_push_url(repo_url)
        if not remote_url:
            return 1, f"Could not parse repo from {repo_url}"
        if not self.base_sha:
            return 1, "No base commit recorded (empty repository?); cannot push."

        code, patch = self._exec_stdout(patch_script(self.base_sha))
        if code != 0:
            return code, "Failed to collect workspace changes for push."
        if not patch.strip():
            return 1, "No changes to push."

        return self._run_helper(
            push_script(
                remote_url, self.base_sha, branch_name, "/tmp/changes.patch", "/tmp/push",
                clean_commit_message(message), author_name, author_email
            ),
            environment=git_auth_env(github_token),
            mount_repo_volume=False,
            files={"changes.patch": patch}
        )

    def cleanup(self):
        container, self.container = self.container, None
        volume_name, self.volume_name = self.volume_name, None
        # Each step is independent: a failed graceful stop must never leak the container or volume
        if container:
            try:
                container.stop(timeout=2)
            except Exception as e:
                logger.warning("Failed to stop container for task %s: %s", self.task_id, e)
            try:
                container.remove(force=True)
            except docker.errors.NotFound:
                pass
            except Exception as e:
                logger.error("Failed to remove container for task %s: %s", self.task_id, e)
        if volume_name:
            try:
                self.client.volumes.get(volume_name).remove(force=True)
            except docker.errors.NotFound:
                pass
            except Exception as e:
                logger.error("Failed to remove volume %s for task %s: %s", volume_name, self.task_id, e)


class SubprocessWorkspace:
    """Fallback workspace for hosts without a Docker daemon (Render, Railway, serverless).

    When the worker runs as root (the default in backend/Dockerfile), every agent command runs as a
    per-task unprivileged UID with a scrubbed environment, so it cannot read the API's environment
    variables (/proc/<pid>/environ), other tasks' workspaces, or root-owned files. Token-bearing git
    operations run as the worker's own user in private directories the agent cannot reach.
    Without root, commands still get a scrubbed environment but share the worker's UID.
    """

    def __init__(self, task_id: int):
        self.task_id = task_id
        self.base_dir: Optional[str] = None
        self.workdir: Optional[str] = None
        self.base_sha: Optional[str] = None
        self.sandbox_uid: Optional[int] = (
            SANDBOX_UID_BASE + (task_id % SANDBOX_UID_RANGE) if os.geteuid() == 0 else None
        )
        if self.sandbox_uid is None:
            logger.warning(
                "SubprocessWorkspace for task %s is not running as root; agent commands share the "
                "worker's UID and only get a scrubbed environment.", task_id
            )

    def _sandbox_env(self) -> dict:
        return {
            "PATH": SANDBOX_PATH,
            "HOME": self.base_dir or self.workdir or "/tmp",
            "LANG": "C.UTF-8",
            "TERM": "dumb",
        }

    def _run(
        self,
        command: str,
        cwd: str,
        env: dict,
        timeout: int,
        as_sandbox: bool
    ) -> Tuple[int, bytes, bytes]:
        """Runs bash in its own process group (timeouts kill everything it spawned)."""
        user_kwargs = {}
        if as_sandbox and self.sandbox_uid is not None:
            user_kwargs = dict(user=self.sandbox_uid, group=self.sandbox_uid, extra_groups=[])
        proc = subprocess.Popen(
            ["bash", "-c", command],
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            **user_kwargs
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            return proc.returncode, stdout, stderr
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = proc.communicate()
            return 124, stdout, stderr

    def _run_trusted_git(self, script: str, github_token: Optional[str], timeout: int = 300) -> Tuple[int, str]:
        """Runs a token-bearing git script as the worker's user in a fresh private directory."""
        private_dir = tempfile.mkdtemp(prefix="nimbus-git-")
        try:
            env = {"PATH": SANDBOX_PATH, "HOME": private_dir, "LANG": "C.UTF-8"}
            env.update(git_auth_env(github_token))
            code, out, err = self._run(script, private_dir, env, timeout, as_sandbox=False)
            output = out.decode("utf-8", errors="replace") + err.decode("utf-8", errors="replace")
            if code == 124:
                output += f"\n[Git operation timed out after {timeout} seconds]"
            return code, output.strip()
        finally:
            shutil.rmtree(private_dir, ignore_errors=True)

    def _hand_over_to_sandbox(self):
        """Gives the per-task UID ownership of its workspace (never following symlinks)."""
        if self.sandbox_uid is None:
            return
        uid = self.sandbox_uid
        os.lchown(self.base_dir, uid, uid)
        for root, dirs, files in os.walk(self.base_dir, followlinks=False):
            for name in dirs + files:
                os.lchown(os.path.join(root, name), uid, uid)

    def setup(
        self,
        repo_url: Optional[str] = None,
        branch_name: Optional[str] = None,
        github_token: Optional[str] = None
    ) -> Tuple[int, str]:
        # Unpredictable, atomically created 0700 dir: nothing can pre-plant symlinks in it
        self.base_dir = tempfile.mkdtemp(prefix=f"nimbus-workspace-{self.task_id}-")
        self.workdir = os.path.join(self.base_dir, "repo")
        logs = []

        if repo_url:
            cleaned_url = repo_url.strip()
            code, out = self._run_trusted_git(
                clone_script(resolve_clone_url(cleaned_url, github_token), self.workdir),
                github_token
            )
            if code != 0:
                return code, f"Failed to clone repository {cleaned_url}: {out}"
            self.base_sha = parse_base_sha(out)
            self._hand_over_to_sandbox()
            logs.append(f"Cloned {cleaned_url}")

            if branch_name:
                code_b, out_b = self.execute_command(
                    f"git checkout -b {shlex.quote(branch_name)}",
                    workdir=self.workdir
                )
                if code_b != 0:
                    return code_b, f"Failed to create branch {branch_name}: {out_b}"
                logs.append(f"Created branch {branch_name}")
        else:
            os.makedirs(self.workdir, exist_ok=True)
            self._hand_over_to_sandbox()
            init_repo = (
                "git init && "
                "git config user.name 'Nimbus Agent' && "
                "git config user.email 'agent@nimbus.ai' && "
                "echo '# Nimbus Task Workspace' > README.md && "
                "git add . && "
                "git commit -m 'Initial workspace commit'"
            )
            if branch_name:
                init_repo += f" && git checkout -b {shlex.quote(branch_name)}"
            code_init, out_init = self.execute_command(init_repo, workdir=self.workdir)
            if code_init != 0:
                return code_init, f"Failed to initialize empty repository: {out_init}"

        return 0, "\n".join(logs)

    def execute_command(self, command: str, workdir: Optional[str] = None, timeout: int = 300) -> Tuple[int, str]:
        target_dir = workdir or self.workdir
        os.makedirs(target_dir, exist_ok=True)
        try:
            code, stdout, stderr = self._run(command, target_dir, self._sandbox_env(), timeout, as_sandbox=True)
        except Exception as e:
            return 1, f"[Execution failed: {e}]"
        if code == 124:
            return 124, f"[Command timed out after {timeout} seconds]"
        out = stdout.decode("utf-8", errors="replace") + stderr.decode("utf-8", errors="replace")
        return code, out.strip()

    def get_diff(self) -> str:
        self.execute_command("git add -N .", workdir=self.workdir)
        code, out = self.execute_command("git diff HEAD", workdir=self.workdir)
        if not out.strip():
            code, out = self.execute_command("git diff", workdir=self.workdir)
        return out.strip()

    def get_file_base64(self, file_path: str) -> Optional[str]:
        """Reads a file as the sandbox user, so agent-planted symlinks can't expose worker files."""
        code, out = self.execute_command(f"base64 -w 0 {shlex.quote(file_path)}", workdir=self.workdir)
        if code == 0 and out.strip():
            return out.strip()
        return None

    def commit_changes(self, message: str = "Nimbus agent automated changes") -> Tuple[int, str]:
        return self.execute_command(
            f"git add -A && git commit -m {shlex.quote(clean_commit_message(message))} || true",
            workdir=self.workdir
        )

    def push_branch(
        self,
        branch_name: str,
        repo_url: str,
        github_token: Optional[str] = None,
        message: str = "Nimbus agent automated changes",
        author_name: str = "Nimbus Agent",
        author_email: str = "agent@nimbus.ai",
        remote_url: Optional[str] = None
    ) -> Tuple[int, str]:
        """Replays the agent's changes onto a fresh private clone and pushes that, never the agent's .git."""
        if not github_token and remote_url is None:
            return 1, "No GitHub token available to push branch."
        remote_url = remote_url or github_push_url(repo_url)
        if not remote_url:
            return 1, f"Could not parse repo from {repo_url}"
        if not self.base_sha:
            return 1, "No base commit recorded (empty repository?); cannot push."

        try:
            code, patch, _ = self._run(
                patch_script(self.base_sha), self.workdir, self._sandbox_env(), 300, as_sandbox=True
            )
        except Exception as e:
            return 1, f"Failed to collect workspace changes for push: {e}"
        if code != 0:
            return code, "Failed to collect workspace changes for push."
        if not patch.strip():
            return 1, "No changes to push."

        patch_dir = tempfile.mkdtemp(prefix="nimbus-patch-")
        try:
            patch_path = os.path.join(patch_dir, "changes.patch")
            with open(patch_path, "wb") as f:
                f.write(patch)
            return self._run_trusted_git(
                push_script(
                    remote_url, self.base_sha, branch_name, patch_path, "push",
                    clean_commit_message(message), author_name, author_email
                ),
                github_token
            )
        finally:
            shutil.rmtree(patch_dir, ignore_errors=True)

    def cleanup(self):
        if self.sandbox_uid is not None:
            _kill_uid_processes(self.sandbox_uid)
        if self.base_dir and os.path.exists(self.base_dir):
            try:
                shutil.rmtree(self.base_dir, ignore_errors=True)
            except Exception as e:
                logger.warning("Failed to cleanup temp workspace: %s", e)


def _kill_uid_processes(uid: int):
    """Kills anything the agent left running under its per-task UID (e.g. background jobs)."""
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            if os.stat(f"/proc/{entry}").st_uid == uid:
                os.kill(int(entry), signal.SIGKILL)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass


def create_workspace(task_id: int):
    """Factory that returns DockerWorkspace if Docker daemon is running, else SubprocessWorkspace."""
    client = get_docker_client()
    if client is not None:
        return DockerWorkspace(task_id=task_id, client=client)
    return SubprocessWorkspace(task_id=task_id)


class UnifiedWorkspace:
    """Unified asynchronous workspace interface wrapping either Docker or Subprocess."""

    def __init__(self, task_id: int, impl=None):
        self.impl = impl or create_workspace(task_id)

    async def asetup(
        self,
        repo_url: Optional[str] = None,
        branch_name: Optional[str] = None,
        github_token: Optional[str] = None
    ) -> Tuple[int, str]:
        return await asyncio.to_thread(self.impl.setup, repo_url, branch_name, github_token)

    async def aexecute_command(
        self,
        command: str,
        workdir: Optional[str] = None,
        timeout: int = 300
    ) -> Tuple[int, str]:
        return await asyncio.to_thread(self.impl.execute_command, command, workdir, timeout)

    async def aget_diff(self) -> str:
        return await asyncio.to_thread(self.impl.get_diff)

    async def aget_file_base64(self, file_path: str) -> Optional[str]:
        return await asyncio.to_thread(self.impl.get_file_base64, file_path)

    async def acommit_changes(self, message: str = "Nimbus agent automated changes") -> Tuple[int, str]:
        return await asyncio.to_thread(self.impl.commit_changes, message)

    async def apush_branch(
        self,
        branch_name: str,
        repo_url: str,
        github_token: Optional[str] = None,
        message: str = "Nimbus agent automated changes",
        author_name: str = "Nimbus Agent",
        author_email: str = "agent@nimbus.ai"
    ) -> Tuple[int, str]:
        return await asyncio.to_thread(
            self.impl.push_branch, branch_name, repo_url, github_token,
            message=message, author_name=author_name, author_email=author_email
        )

    async def acleanup(self):
        await asyncio.to_thread(self.impl.cleanup)
