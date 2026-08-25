import pytest
from unittest.mock import MagicMock, patch
from app.workspace import DockerWorkspace


@patch("docker.from_env")
def test_docker_workspace_init(mock_docker_env):
    mock_client = MagicMock()
    mock_docker_env.return_value = mock_client

    ws = DockerWorkspace(task_id=42, image="ubuntu:22.04")
    assert ws.task_id == 42
    assert ws.image == "ubuntu:22.04"
    assert ws.workdir == "/workspace/repo"
    assert ws.container is None


@patch("docker.from_env")
def test_docker_workspace_setup_with_repo(mock_docker_env):
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.short_id = "abc1234"
    mock_client.containers.run.return_value = mock_container
    mock_docker_env.return_value = mock_client

    ws = DockerWorkspace(task_id=10)
    # Mock execute_command to simulate successful git commands
    ws.execute_command = MagicMock(return_value=(0, "Success"))

    code, logs = ws.setup(
        repo_url="https://github.com/octocat/Hello-World",
        branch_name="nimbus/task-10",
        github_token="ghp_test_token"
    )

    assert code == 0
    assert ws.container == mock_container
    assert ws.execute_command.called


@patch("docker.from_env")
def test_docker_workspace_setup_empty_repo(mock_docker_env):
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.short_id = "def5678"
    mock_client.containers.run.return_value = mock_container
    mock_docker_env.return_value = mock_client

    ws = DockerWorkspace(task_id=20)
    ws.execute_command = MagicMock(return_value=(0, "Initialized"))

    code, logs = ws.setup(repo_url=None, branch_name="nimbus/task-20")
    assert code == 0
    assert ws.container == mock_container
    assert ws.execute_command.called


@patch("docker.from_env")
def test_docker_workspace_execute_command(mock_docker_env):
    mock_client = MagicMock()
    mock_container = MagicMock()
    
    exec_result = MagicMock()
    exec_result.exit_code = 0
    exec_result.output = (b"hello world\n", None)
    mock_container.exec_run.return_value = exec_result

    mock_docker_env.return_value = mock_client

    ws = DockerWorkspace(task_id=30)
    ws.container = mock_container

    code, out = ws.execute_command("echo 'hello world'")
    assert code == 0
    assert out == "hello world"
    mock_container.exec_run.assert_called_once()


@patch("docker.from_env")
def test_docker_workspace_cleanup(mock_docker_env):
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_docker_env.return_value = mock_client

    ws = DockerWorkspace(task_id=40)
    ws.container = mock_container

    ws.cleanup()
    mock_container.stop.assert_called_once_with(timeout=2)
    mock_container.remove.assert_called_once_with(force=True)
    assert ws.container is None
