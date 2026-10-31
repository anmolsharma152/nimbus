import base64
import io
import subprocess
import tarfile
import time
from unittest.mock import MagicMock, patch

import docker
import pytest

from app.workspace import (
    DockerWorkspace,
    SubprocessWorkspace,
    WORKSPACE_USER,
    git_auth_env,
    reap_orphaned_volumes,
)

TOKEN = "ghp_canaryTokenForSandboxTests000000"
AUTH_HEADER = base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode()
BASE_SHA = "a" * 40


def _docker_client(helper_status=0, helper_logs=b"Cloning into '/workspace/repo'...\n" + BASE_SHA.encode()):
    client = MagicMock()
    client.volumes.create.return_value.name = "nimbus-task-1-vol"
    helper = client.containers.create.return_value
    helper.wait.return_value = {"StatusCode": helper_status}
    helper.logs.return_value = helper_logs
    return client, helper


def _assert_no_token(obj):
    text = str(obj)
    assert TOKEN not in text
    assert AUTH_HEADER not in text


# --- git auth env ---

def test_git_auth_env_disables_hooks_and_scopes_header_to_github():
    env = git_auth_env(TOKEN)
    pairs = {env[f"GIT_CONFIG_KEY_{i}"]: env[f"GIT_CONFIG_VALUE_{i}"] for i in range(int(env["GIT_CONFIG_COUNT"]))}
    assert pairs["core.hooksPath"] == "/dev/null"
    assert pairs["http.https://github.com/.extraheader"] == f"AUTHORIZATION: basic {AUTH_HEADER}"
    assert "http.extraheader" not in pairs

    no_token = git_auth_env(None)
    assert no_token["GIT_CONFIG_COUNT"] == "1"
    _assert_no_token(no_token)


# --- Docker mode ---

def test_agent_container_is_unprivileged_and_never_sees_token():
    client, _ = _docker_client()
    ws = DockerWorkspace(task_id=1, client=client)
    ws.execute_command = MagicMock(return_value=(0, ""))

    code, _ = ws.setup(repo_url="https://github.com/o/r", branch_name="nimbus/task-1", github_token=TOKEN)

    assert code == 0
    assert ws.base_sha == BASE_SHA
    kwargs = client.containers.run.call_args.kwargs
    assert client.containers.run.call_args.args[0] == "nimbus-workspace:latest"
    assert kwargs["user"] == WORKSPACE_USER
    assert kwargs["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in kwargs["security_opt"]
    assert kwargs["pids_limit"] == 256
    assert kwargs["mem_limit"] == "1g"
    assert kwargs["nano_cpus"] == 2_000_000_000
    assert kwargs["volumes"] == {"nimbus-task-1-vol": {"bind": "/workspace", "mode": "rw"}}
    assert "environment" not in kwargs
    _assert_no_token(client.containers.run.call_args)
    _assert_no_token(ws.execute_command.call_args_list)


def test_clone_runs_in_helper_with_token_only_in_env_before_agent_starts():
    client, helper = _docker_client()
    ws = DockerWorkspace(task_id=1, client=client)
    ws.execute_command = MagicMock(return_value=(0, ""))

    ws.setup(repo_url="https://github.com/o/r", github_token=TOKEN)

    create_kwargs = client.containers.create.call_args.kwargs
    assert create_kwargs["user"] == WORKSPACE_USER
    assert create_kwargs["cap_drop"] == ["ALL"]
    assert AUTH_HEADER in str(create_kwargs["environment"])
    _assert_no_token(create_kwargs["command"])
    helper.remove.assert_called_once_with(force=True)

    calls = [str(c) for c in client.mock_calls]
    helper_removed = next(i for i, c in enumerate(calls) if "containers.create().remove" in c)
    agent_started = next(i for i, c in enumerate(calls) if c.startswith("call.containers.run("))
    assert helper_removed < agent_started


def test_failed_clone_removes_helper_and_never_starts_agent():
    client, helper = _docker_client(helper_status=128, helper_logs=b"fatal: repository not found")
    ws = DockerWorkspace(task_id=1, client=client)

    code, out = ws.setup(repo_url="https://github.com/o/missing", github_token=TOKEN)

    assert code == 128
    assert "repository not found" in out
    assert not client.containers.run.called
    helper.remove.assert_called_once_with(force=True)


def test_missing_workspace_image_fails_with_build_hint():
    client = MagicMock()
    client.images.get.side_effect = docker.errors.ImageNotFound("nope")
    client.images.pull.side_effect = docker.errors.APIError("pull access denied")
    ws = DockerWorkspace(task_id=1, client=client)

    code, out = ws.setup(repo_url="https://github.com/o/r")

    assert code == 1
    assert "docker build -f backend/Dockerfile.workspace" in out
    assert not client.containers.run.called
    assert not client.volumes.create.called


def test_push_replays_patch_in_fresh_helper_without_agent_volume():
    client, helper = _docker_client(helper_logs=b"")
    ws = DockerWorkspace(task_id=1, client=client)
    ws.container = MagicMock()
    ws.volume_name = "nimbus-task-1-vol"
    ws.base_sha = BASE_SHA
    patch_bytes = b"diff --git a/x.py b/x.py\nnew file mode 100644\n"
    ws.container.exec_run.return_value = MagicMock(exit_code=0, output=(patch_bytes, None))

    code, _ = ws.push_branch(
        "nimbus/task-1", "https://github.com/o/r", TOKEN,
        message="Nimbus: fix", author_name="Dev", author_email="dev@example.com"
    )

    assert code == 0
    create_kwargs = client.containers.create.call_args.kwargs
    assert create_kwargs["volumes"] is None  # the agent's .git is never mounted into the token holder
    assert AUTH_HEADER in str(create_kwargs["environment"])
    script = create_kwargs["command"][2]
    assert f"git fetch -q --depth 1 origin {BASE_SHA}" in script
    assert "git apply --index /tmp/changes.patch" in script
    _assert_no_token(script)
    _assert_no_token(ws.container.exec_run.call_args_list)

    archive = helper.put_archive.call_args.args[1]
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        assert tar.extractfile("changes.patch").read() == patch_bytes
    helper.remove.assert_called_once_with(force=True)


def test_push_without_base_commit_is_refused():
    client, _ = _docker_client()
    ws = DockerWorkspace(task_id=1, client=client)
    ws.container = MagicMock()

    code, out = ws.push_branch("b", "https://github.com/o/r", TOKEN)

    assert code == 1
    assert "No base commit" in out
    assert not client.containers.create.called


def test_cleanup_removes_volume_even_without_container():
    client = MagicMock()
    ws = DockerWorkspace(task_id=1, client=client)
    ws.volume_name = "nimbus-task-1-vol"

    ws.cleanup()

    client.volumes.get.assert_called_once_with("nimbus-task-1-vol")
    client.volumes.get.return_value.remove.assert_called_once_with(force=True)
    assert ws.volume_name is None


def test_volume_reaper_removes_only_expired_volumes():
    now = int(time.time())
    expired = MagicMock(attrs={"Labels": {"nimbus.created": str(now - 10_000)}})
    live = MagicMock(attrs={"Labels": {"nimbus.created": str(now - 60)}})
    client = MagicMock()
    client.volumes.list.return_value = [expired, live]

    assert reap_orphaned_volumes(client, max_age_seconds=3600) == 1
    expired.remove.assert_called_once_with(force=True)
    assert not live.remove.called


# --- Subprocess mode ---

def _git(*args, cwd=None):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def bare_remote(tmp_path):
    """A local bare repo with one commit, standing in for GitHub."""
    src = tmp_path / "src"
    src.mkdir()
    _git("init", "-q", "-b", "main", cwd=src)
    (src / "README.md").write_text("hello\n")
    _git("add", ".", cwd=src)
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init", cwd=src)
    bare = tmp_path / "remote.git"
    _git("clone", "-q", "--bare", str(src), str(bare))
    # GitHub allows fetching a commit by SHA; mirror that for the local stand-in
    _git("config", "uploadpack.allowReachableSHA1InWant", "true", cwd=bare)
    return bare


def test_subprocess_commands_get_scrubbed_environment(monkeypatch):
    monkeypatch.setenv("NIMBUS_CANARY_SECRET", "leak-me")
    ws = SubprocessWorkspace(task_id=4242)
    try:
        code, _ = ws.setup()
        assert code == 0
        code, out = ws.execute_command("env")
        assert code == 0
        assert "leak-me" not in out
        assert f"HOME={ws.base_dir}" in out
        assert set(line.split("=", 1)[0] for line in out.splitlines()) <= {"PATH", "HOME", "LANG", "TERM", "PWD", "SHLVL", "_", "OLDPWD"}
    finally:
        ws.cleanup()


def test_subprocess_push_ignores_agent_controlled_git_config_and_hooks(bare_remote, tmp_path):
    remote_url = f"file://{bare_remote}"
    marker = tmp_path / "hook-ran"
    ws = SubprocessWorkspace(task_id=4243)
    try:
        code, out = ws.setup(repo_url=remote_url, branch_name="nimbus/task-4243")
        assert code == 0, out
        assert ws.base_sha and len(ws.base_sha) == 40

        # Agent makes a change and tries to hijack any later token-bearing git command
        ws.execute_command("echo 'print(1)' > fix.py")
        ws.execute_command(f"git config url.file:///nonexistent/evil.git.insteadOf {remote_url}")
        ws.execute_command(
            f"printf '#!/bin/sh\\ntouch {marker}\\n' > .git/hooks/pre-push && chmod +x .git/hooks/pre-push"
        )
        ws.commit_changes("agent commit")

        code, out = ws.push_branch(
            "nimbus/task-4243", "https://github.com/o/r", None,
            message="Nimbus: add fix", author_name="Dev", author_email="dev@example.com",
            remote_url=remote_url
        )
        assert code == 0, out
    finally:
        ws.cleanup()

    assert not marker.exists()
    shown = subprocess.run(
        ["git", "log", "-1", "--format=%an <%ae>|%s", "nimbus/task-4243"],
        cwd=bare_remote, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert shown == "Dev <dev@example.com>|Nimbus: add fix"
    content = subprocess.run(
        ["git", "show", "nimbus/task-4243:fix.py"], cwd=bare_remote, capture_output=True, text=True, check=True
    ).stdout
    assert content == "print(1)\n"


def _fake_popen():
    proc = MagicMock(returncode=0, pid=99999)
    proc.communicate.return_value = (b"", b"")
    return MagicMock(return_value=proc)


def test_root_worker_runs_agent_commands_as_per_task_uid(tmp_path):
    with patch("app.workspace.os.geteuid", return_value=0):
        ws = SubprocessWorkspace(task_id=7)
    ws.workdir = str(tmp_path)

    with patch("app.workspace.subprocess.Popen", _fake_popen()) as popen:
        ws.execute_command("id")

    kwargs = popen.call_args.kwargs
    assert kwargs["user"] == kwargs["group"] == 200_007
    assert kwargs["extra_groups"] == []
    assert set(kwargs["env"]) == {"PATH", "HOME", "LANG", "TERM"}


def test_token_bearing_git_never_runs_as_sandbox_uid():
    with patch("app.workspace.os.geteuid", return_value=0):
        ws = SubprocessWorkspace(task_id=7)

    with patch("app.workspace.subprocess.Popen", _fake_popen()) as popen:
        ws._run_trusted_git("git ls-remote origin", TOKEN)

    kwargs = popen.call_args.kwargs
    assert "user" not in kwargs
    assert AUTH_HEADER in str(kwargs["env"])
    _assert_no_token(popen.call_args.args)


def test_cleanup_kills_leftover_sandbox_processes():
    with patch("app.workspace.os.geteuid", return_value=0):
        ws = SubprocessWorkspace(task_id=7)
    with patch("app.workspace._kill_uid_processes") as kill:
        ws.cleanup()
    kill.assert_called_once_with(200_007)


def _remote_sha(bare, ref):
    return subprocess.run(
        ["git", "rev-parse", ref], cwd=bare, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_push_never_updates_an_existing_remote_branch(bare_remote):
    """Even if a protected name slipped past validation, the push refuses to touch an existing branch."""
    remote_url = f"file://{bare_remote}"
    main_before = _remote_sha(bare_remote, "main")
    ws = SubprocessWorkspace(task_id=4244)
    try:
        code, out = ws.setup(repo_url=remote_url, branch_name="nimbus/task-4244")
        assert code == 0, out
        ws.execute_command("echo change > new.txt")
        ws.commit_changes("agent commit")

        # Fast-forwarding main would succeed with a plain `git push`
        code, _ = ws.push_branch("main", "https://github.com/o/r", None, remote_url=remote_url)
        assert code != 0
        assert _remote_sha(bare_remote, "main") == main_before

        code, out = ws.push_branch("nimbus/task-4244", "https://github.com/o/r", None, remote_url=remote_url)
        assert code == 0, out
        # A second, different push to the now-existing branch is refused as well
        ws.execute_command("echo more >> new.txt")
        ws.commit_changes("agent commit 2")
        pushed = _remote_sha(bare_remote, "nimbus/task-4244")
        code, _ = ws.push_branch("nimbus/task-4244", "https://github.com/o/r", None, remote_url=remote_url)
        assert code != 0
        assert _remote_sha(bare_remote, "nimbus/task-4244") == pushed
    finally:
        ws.cleanup()


def test_push_to_stale_fork_builds_on_upstream_base(bare_remote, tmp_path):
    """Without write access the branch goes to the user's fork, which may lack the base commit."""
    fork = tmp_path / "fork.git"
    _git("clone", "-q", "--bare", str(bare_remote), str(fork))
    # Upstream moves on after the fork was made
    work = tmp_path / "up"
    _git("clone", "-q", str(bare_remote), str(work))
    (work / "later.txt").write_text("later\n")
    _git("add", ".", cwd=work)
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "later", cwd=work)
    _git("push", "-q", "origin", "main", cwd=work)
    upstream_head = _remote_sha(bare_remote, "main")
    fork_main = _remote_sha(fork, "main")
    assert fork_main != upstream_head

    remote_url = f"file://{bare_remote}"
    ws = SubprocessWorkspace(task_id=4245)
    try:
        code, out = ws.setup(repo_url=remote_url, branch_name="nimbus/task-4245")
        assert code == 0, out
        assert ws.base_sha == upstream_head
        ws.execute_command("echo fix > fix.txt")
        ws.commit_changes("agent commit")
        code, out = ws.push_branch(
            "nimbus/task-4245", "https://github.com/o/r", None,
            remote_url=remote_url, push_url=f"file://{fork}"
        )
        assert code == 0, out
    finally:
        ws.cleanup()

    assert _remote_sha(fork, "nimbus/task-4245^") == upstream_head
    assert _remote_sha(fork, "main") == fork_main  # fork's own branches untouched
    with pytest.raises(subprocess.CalledProcessError):
        _remote_sha(bare_remote, "nimbus/task-4245")  # nothing pushed upstream


def test_follow_up_rebuilds_state_and_replaces_only_its_own_push(bare_remote):
    """Turn 2 starts from turn 1's base + patch, and the push replaces turn 1's commit via the lease."""
    remote_url = f"file://{bare_remote}"
    branch = "nimbus/task-4246"

    ws = SubprocessWorkspace(task_id=4246)
    try:
        assert ws.setup(repo_url=remote_url, branch_name=branch)[0] == 0
        base = ws.base_sha
        ws.execute_command("echo one > one.txt")
        prior_patch = ws.get_diff()
        ws.commit_changes("turn 1")
        code, out = ws.push_branch(branch, "https://github.com/o/r", None, remote_url=remote_url)
        assert code == 0, out
        first_push = out.strip().splitlines()[-1]
    finally:
        ws.cleanup()
    assert _remote_sha(bare_remote, branch) == first_push

    # Upstream moves on; the follow-up must still build on the task's original base
    work = bare_remote.parent / "mover"
    _git("clone", "-q", str(bare_remote), str(work))
    (work / "other.txt").write_text("x\n")
    _git("add", ".", cwd=work)
    _git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "other", cwd=work)
    _git("push", "-q", "origin", "main", cwd=work)

    ws = SubprocessWorkspace(task_id=4247)
    try:
        assert ws.setup(repo_url=remote_url, branch_name=branch, start_point=base)[0] == 0
        assert ws.base_sha == base
        code, out = ws.apply_patch(prior_patch)
        assert code == 0, out
        ws.execute_command("echo two > two.txt")
        ws.commit_changes("turn 2")

        # Wrong expectation (someone else pushed): refused
        code, _ = ws.push_branch(branch, "https://github.com/o/r", None, remote_url=remote_url, expect_sha=base)
        assert code != 0
        assert _remote_sha(bare_remote, branch) == first_push

        code, out = ws.push_branch(branch, "https://github.com/o/r", None, remote_url=remote_url, expect_sha=first_push)
        assert code == 0, out
    finally:
        ws.cleanup()

    head = _remote_sha(bare_remote, branch)
    assert head != first_push
    assert _remote_sha(bare_remote, f"{branch}^") == base
    files = subprocess.run(
        ["git", "ls-tree", "--name-only", head], cwd=bare_remote, capture_output=True, text=True, check=True
    ).stdout.split()
    assert {"one.txt", "two.txt"} <= set(files) and "other.txt" not in files


def test_setup_rejects_non_sha_start_point():
    ws = SubprocessWorkspace(task_id=4248)
    with pytest.raises(ValueError):
        ws.setup(repo_url="file:///nonexistent", branch_name="b", start_point="main; rm -rf /")
