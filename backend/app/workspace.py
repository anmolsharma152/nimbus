import docker
from docker.models.containers import Container
from typing import Optional, Tuple
import time
import re
from .github_client import parse_github_repo


class DockerWorkspace:
    """Manages an ephemeral Docker container for agent tasks with repository and git support."""
    
    def __init__(self, task_id: int, image: str = "ubuntu:latest"):
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
        """Pulls the image, starts the container, provisions git environment, and clones repo."""
        try:
            self.client.images.get(self.image)
        except docker.errors.ImageNotFound:
            print(f"Pulling image {self.image}...")
            self.client.images.pull(self.image)

        # Start the container in detached mode
        self.container = self.client.containers.run(
            self.image,
            command="tail -f /dev/null",
            detach=True,
            name=f"nimbus-task-{self.task_id}-{int(time.time())}",
            working_dir="/workspace"
        )
        
        # Ensure packages and git identity
        init_commands = (
            "mkdir -p /workspace && "
            "apt-get update && "
            "apt-get install -y git curl python3 build-essential && "
            "git config --global user.name 'Nimbus Agent' && "
            "git config --global user.email 'agent@nimbus.ai' && "
            "git config --global --add safe.directory '*'"
        )
        self.execute_command(init_commands, workdir="/workspace")

        logs = []
        if repo_url:
            clone_target = repo_url.strip()
            # If token is provided, embed it into the clone URL for authenticated cloning
            if github_token:
                parsed = parse_github_repo(repo_url)
                if parsed:
                    owner, repo = parsed
                    clone_target = f"https://x-access-token:{github_token}@github.com/{owner}/{repo}.git"

            code, out = self.execute_command(f"git clone {clone_target} /workspace/repo", workdir="/workspace")
            logs.append(f"Cloned {repo_url}: {out}")

            if branch_name:
                code_b, out_b = self.execute_command(f"git checkout -b {branch_name}", workdir="/workspace/repo")
                logs.append(f"Created branch {branch_name}: {out_b}")
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
                init_repo += f" && git checkout -b {branch_name}"
            self.execute_command(init_repo, workdir="/workspace")
            self.workdir = "/workspace/repo"

        print(f"Workspace for task {self.task_id} initialized: {self.container.short_id}")
        return 0, "\n".join(logs)

    def execute_command(self, command: str, workdir: Optional[str] = None) -> Tuple[int, str]:
        """Executes a bash command inside the container and returns (exit_code, output)."""
        if not self.container:
            raise RuntimeError("Workspace is not set up.")
        
        target_dir = workdir or self.workdir
        bash_cmd = ["bash", "-c", command]
        
        exec_result = self.container.exec_run(
            cmd=bash_cmd,
            workdir=target_dir,
            demux=True
        )
        
        exit_code = exec_result.exit_code
        stdout = exec_result.output[0] or b""
        stderr = exec_result.output[1] or b""
        
        output = stdout.decode('utf-8', errors='replace') + stderr.decode('utf-8', errors='replace')
        return exit_code, output.strip()

    def get_diff(self) -> str:
        """Returns the full git diff for changes in the workspace repository."""
        if not self.container:
            return ""
        # Stage untracked files to see full diff or get diff against HEAD
        self.execute_command("git add -N .", workdir=self.workdir)
        code, out = self.execute_command("git diff HEAD", workdir=self.workdir)
        if not out.strip():
            code, out = self.execute_command("git diff", workdir=self.workdir)
        return out.strip()

    def commit_changes(self, message: str = "Nimbus agent automated changes") -> Tuple[int, str]:
        """Stages all changed files and commits them."""
        return self.execute_command(
            f"git add -A && git commit -m '{message}' || true",
            workdir=self.workdir
        )

    def push_branch(
        self,
        branch_name: str,
        repo_url: str,
        github_token: Optional[str] = None
    ) -> Tuple[int, str]:
        """Pushes the feature branch to origin."""
        if not github_token:
            return 1, "No GitHub token available to push branch."

        parsed = parse_github_repo(repo_url)
        if not parsed:
            return 1, f"Could not parse repo from {repo_url}"

        owner, repo = parsed
        push_url = f"https://x-access-token:{github_token}@github.com/{owner}/{repo}.git"
        return self.execute_command(
            f"git push {push_url} {branch_name}",
            workdir=self.workdir
        )

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
