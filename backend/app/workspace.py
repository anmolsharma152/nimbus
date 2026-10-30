import os
import shutil
import signal
import asyncio
import logging
import subprocess
import threading
import time
from typing import Optional, Tuple
import shlex
import base64
from .github_client import parse_github_repo

try:
    import docker
    from docker.models.containers import Container
    DOCKER_LIB_INSTALLED = True
except ImportError:
    DOCKER_LIB_INSTALLED = False

logger = logging.getLogger(__name__)

MANAGED_LABEL = "nimbus.managed"

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


class DockerWorkspace:
    """Manages an ephemeral Docker container for agent tasks when Docker daemon is reachable."""

    def __init__(self, task_id: int, image: str = "ubuntu:22.04", client=None):
        self.task_id = task_id
        self.image = image
        self.client = client or get_docker_client() or docker.from_env()
        self.container: Optional[Container] = None
        self.workdir: str = "/workspace/repo"

    def setup(
        self,
        repo_url: Optional[str] = None,
        branch_name: Optional[str] = None,
        github_token: Optional[str] = None
    ) -> Tuple[int, str]:
        try:
            self.client.images.get(self.image)
        except docker.errors.ImageNotFound:
            print(f"Pulling image {self.image}...")
            self.client.images.pull(self.image)

        self.container = self.client.containers.run(
            self.image,
            command="tail -f /dev/null",
            detach=True,
            name=f"nimbus-task-{self.task_id}-{int(time.time())}",
            working_dir="/workspace",
            mem_limit="1g",
            nano_cpus=2_000_000_000,
            pids_limit=256,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            labels={
                MANAGED_LABEL: "true",
                "nimbus.task_id": str(self.task_id),
                "nimbus.created": str(int(time.time())),
            }
        )
        
        init_commands = (
            "mkdir -p /workspace && "
            "(which git >/dev/null 2>&1 || (apt-get update && apt-get install -y --no-install-recommends git curl python3 build-essential)) && "
            "git config --global user.name 'Nimbus Agent' && "
            "git config --global user.email 'agent@nimbus.ai' && "
            "git config --global --add safe.directory '*'"
        )
        code, out = self.execute_command(init_commands, workdir="/workspace")
        if code != 0:
            return code, f"Failed to initialize workspace environment: {out}"

        logs = []
        if repo_url:
            cleaned_url = repo_url.strip()
            if github_token:
                parsed = parse_github_repo(cleaned_url)
                if parsed:
                    owner, repo = parsed
                    auth_header = base64.b64encode(f"x-access-token:{github_token}".encode()).decode()
                    clone_cmd = (
                        f"git -c http.extraheader='AUTHORIZATION: basic {auth_header}' "
                        f"clone https://github.com/{shlex.quote(owner)}/{shlex.quote(repo)}.git /workspace/repo"
                    )
                else:
                    clone_cmd = f"git clone {shlex.quote(cleaned_url)} /workspace/repo"
            else:
                clone_cmd = f"git clone {shlex.quote(cleaned_url)} /workspace/repo"

            code, out = self.execute_command(clone_cmd, workdir="/workspace")
            if code != 0:
                return code, f"Failed to clone repository {cleaned_url}: {out}"
            logs.append(f"Cloned {cleaned_url}")

            if branch_name:
                code_b, out_b = self.execute_command(
                    f"git checkout -b {shlex.quote(branch_name)}",
                    workdir="/workspace/repo"
                )
                if code_b != 0:
                    return code_b, f"Failed to create branch {branch_name}: {out_b}"
                logs.append(f"Created branch {branch_name}")
            self.workdir = "/workspace/repo"
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
            self.workdir = "/workspace/repo"

        return 0, "\n".join(logs)

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
        github_token: Optional[str] = None
    ) -> Tuple[int, str]:
        if not github_token:
            return 1, "No GitHub token available to push branch."

        parsed = parse_github_repo(repo_url)
        if not parsed:
            return 1, f"Could not parse repo from {repo_url}"

        owner, repo = parsed
        auth_header = base64.b64encode(f"x-access-token:{github_token}".encode()).decode()
        push_cmd = (
            f"git -c http.extraheader='AUTHORIZATION: basic {auth_header}' "
            f"push https://github.com/{shlex.quote(owner)}/{shlex.quote(repo)}.git {shlex.quote(branch_name)}"
        )
        return self.execute_command(push_cmd, workdir=self.workdir)

    def cleanup(self):
        container, self.container = self.container, None
        if not container:
            return
        # stop and remove are independent: a failed graceful stop must never leak the container
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


class SubprocessWorkspace:
    """Fallback ephemeral workspace for cloud environments without nested Docker daemon (Render, serverless)."""

    def __init__(self, task_id: int):
        self.task_id = task_id
        self.base_dir = f"/tmp/nimbus-workspace-{self.task_id}"
        self.workdir = os.path.join(self.base_dir, "repo")

    def setup(
        self,
        repo_url: Optional[str] = None,
        branch_name: Optional[str] = None,
        github_token: Optional[str] = None
    ) -> Tuple[int, str]:
        os.makedirs(self.base_dir, exist_ok=True)
        logs = []

        if repo_url:
            cleaned_url = repo_url.strip()
            if os.path.exists(self.workdir):
                shutil.rmtree(self.workdir, ignore_errors=True)
                
            if github_token:
                parsed = parse_github_repo(cleaned_url)
                if parsed:
                    owner, repo = parsed
                    auth_header = base64.b64encode(f"x-access-token:{github_token}".encode()).decode()
                    clone_cmd = (
                        f"git -c http.extraheader='AUTHORIZATION: basic {auth_header}' "
                        f"clone https://github.com/{shlex.quote(owner)}/{shlex.quote(repo)}.git {shlex.quote(self.workdir)}"
                    )
                else:
                    clone_cmd = f"git clone {shlex.quote(cleaned_url)} {shlex.quote(self.workdir)}"
            else:
                clone_cmd = f"git clone {shlex.quote(cleaned_url)} {shlex.quote(self.workdir)}"

            code, out = self.execute_command(clone_cmd, workdir=self.base_dir)
            if code != 0:
                return code, f"Failed to clone repository {cleaned_url}: {out}"
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
            # Own process group so a timeout kills everything the command spawned, not just bash
            proc = subprocess.Popen(
                ["bash", "-c", command],
                cwd=target_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True
            )
        except Exception as e:
            return 1, f"[Execution failed: {e}]"
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            out = (stdout or "") + (stderr or "")
            return proc.returncode, out.strip()
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.communicate()
            return 124, f"[Command timed out after {timeout} seconds]"
        except Exception as e:
            proc.kill()
            proc.communicate()
            return 1, f"[Execution failed: {e}]"

    def get_diff(self) -> str:
        self.execute_command("git add -N .", workdir=self.workdir)
        code, out = self.execute_command("git diff HEAD", workdir=self.workdir)
        if not out.strip():
            code, out = self.execute_command("git diff", workdir=self.workdir)
        return out.strip()

    def get_file_base64(self, file_path: str) -> Optional[str]:
        """Reads a binary file inside local subprocess workdir and returns its base64 encoded string."""
        full_path = os.path.join(self.workdir, file_path) if not os.path.isabs(file_path) else file_path
        if os.path.exists(full_path):
            try:
                with open(full_path, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                return None
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
        github_token: Optional[str] = None
    ) -> Tuple[int, str]:
        if not github_token:
            return 1, "No GitHub token available to push branch."

        parsed = parse_github_repo(repo_url)
        if not parsed:
            return 1, f"Could not parse repo from {repo_url}"

        owner, repo = parsed
        auth_header = base64.b64encode(f"x-access-token:{github_token}".encode()).decode()
        push_cmd = (
            f"git -c http.extraheader='AUTHORIZATION: basic {auth_header}' "
            f"push https://github.com/{shlex.quote(owner)}/{shlex.quote(repo)}.git {shlex.quote(branch_name)}"
        )
        return self.execute_command(push_cmd, workdir=self.workdir)

    def cleanup(self):
        if os.path.exists(self.base_dir):
            try:
                shutil.rmtree(self.base_dir, ignore_errors=True)
            except Exception as e:
                print(f"Failed to cleanup temp workspace: {e}")


def create_workspace(task_id: int):
    """Factory that returns DockerWorkspace if Docker daemon is running, else SubprocessWorkspace."""
    client = get_docker_client()
    if client is not None:
        return DockerWorkspace(task_id=task_id, client=client)
    return SubprocessWorkspace(task_id=task_id)


class UnifiedWorkspace:
    """Unified asynchronous workspace interface wrapping either Docker or Subprocess."""

    def __init__(self, task_id: int):
        self.impl = create_workspace(task_id)

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
        github_token: Optional[str] = None
    ) -> Tuple[int, str]:
        return await asyncio.to_thread(self.impl.push_branch, branch_name, repo_url, github_token)

    async def acleanup(self):
        await asyncio.to_thread(self.impl.cleanup)
