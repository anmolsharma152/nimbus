import docker
from docker.models.containers import Container
from typing import Optional, Tuple
import asyncio
import time
import shlex
import base64
from .github_client import parse_github_repo


class DockerWorkspace:
    """Manages an ephemeral, resource-constrained Docker container for agent tasks with git support."""
    
    def __init__(self, task_id: int, image: str = "ubuntu:22.04"):
        self.task_id = task_id
        self.image = image
        self.client = docker.from_env()
        self.container: Optional[Container] = None
        self.workdir: str = "/workspace/repo"

    def setup(
        self,
        repo_url: Optional[str] = None,
        branch_name: Optional[str] = None,
        github_token: Optional[str] = None
    ) -> Tuple[int, str]:
        """Starts a sandboxed container with resource limits, provisions git environment, and clones repo."""
        try:
            self.client.images.get(self.image)
        except docker.errors.ImageNotFound:
            print(f"Pulling image {self.image}...")
            self.client.images.pull(self.image)

        # Start the container with strict resource limits & sandbox security
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
            security_opt=["no-new-privileges:true"]
        )
        
        # Ensure packages and git identity (fast check if pre-installed)
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
            # If token is provided, authenticate via HTTP header to avoid saving token in .git/config
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
            # Initialize empty git repo in /workspace/repo
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

        print(f"Workspace for task {self.task_id} initialized: {self.container.short_id}")
        return 0, "\n".join(logs)

    def execute_command(self, command: str, workdir: Optional[str] = None, timeout: int = 300) -> Tuple[int, str]:
        """Executes a bash command inside the container with timeout and returns (exit_code, output)."""
        if not self.container:
            raise RuntimeError("Workspace is not set up.")
        
        target_dir = workdir or self.workdir
        # Wrap command with timeout to prevent hanging processes
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
        """Returns the full git diff for changes in the workspace repository."""
        if not self.container:
            return ""
        # Stage untracked files with intent-to-add so diff captures newly created files
        self.execute_command("git add -N .", workdir=self.workdir)
        code, out = self.execute_command("git diff HEAD", workdir=self.workdir)
        if not out.strip():
            code, out = self.execute_command("git diff", workdir=self.workdir)
        return out.strip()

    def commit_changes(self, message: str = "Nimbus agent automated changes") -> Tuple[int, str]:
        """Stages all changed files and commits them with sanitized commit message."""
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
        """Pushes the feature branch to origin without embedding token into git remote config."""
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
        """Stops and removes the container."""
        if self.container:
            try:
                self.container.stop(timeout=2)
                self.container.remove(force=True)
                print(f"Workspace for task {self.task_id} cleaned up.")
            except Exception as e:
                print(f"Failed to cleanup workspace: {e}")
            finally:
                self.container = None

    # Asynchronous non-blocking wrappers for production event-loop concurrency
    async def asetup(
        self,
        repo_url: Optional[str] = None,
        branch_name: Optional[str] = None,
        github_token: Optional[str] = None
    ) -> Tuple[int, str]:
        """Asynchronously provisions the Docker workspace in a background thread."""
        return await asyncio.to_thread(self.setup, repo_url, branch_name, github_token)

    async def aexecute_command(
        self,
        command: str,
        workdir: Optional[str] = None,
        timeout: int = 300
    ) -> Tuple[int, str]:
        """Asynchronously executes a command inside the container without blocking the event loop."""
        return await asyncio.to_thread(self.execute_command, command, workdir, timeout)

    async def aget_diff(self) -> str:
        """Asynchronously retrieves git diff without blocking the event loop."""
        return await asyncio.to_thread(self.get_diff)

    async def acommit_changes(self, message: str = "Nimbus agent automated changes") -> Tuple[int, str]:
        """Asynchronously commits changes without blocking the event loop."""
        return await asyncio.to_thread(self.commit_changes, message)

    async def apush_branch(
        self,
        branch_name: str,
        repo_url: str,
        github_token: Optional[str] = None
    ) -> Tuple[int, str]:
        """Asynchronously pushes branch to GitHub without blocking the event loop."""
        return await asyncio.to_thread(self.push_branch, branch_name, repo_url, github_token)

    async def acleanup(self):
        """Asynchronously cleans up container resources without blocking the event loop."""
        await asyncio.to_thread(self.cleanup)
