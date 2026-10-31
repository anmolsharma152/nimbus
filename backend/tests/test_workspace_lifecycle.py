import asyncio
import os
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import docker

from app import workspace
from app.workspace import (
    DockerWorkspace,
    SubprocessWorkspace,
    create_workspace,
    get_docker_client,
    reap_orphaned_containers,
)
from app.models import Task, TaskStatus


# --- Shared Docker client ---

@patch("docker.from_env")
def test_docker_client_is_shared_across_workspaces(mock_from_env):
    mock_from_env.return_value = MagicMock()

    create_workspace(1)
    create_workspace(2)
    DockerWorkspace(task_id=3)

    assert mock_from_env.call_count == 1


@patch("docker.from_env")
def test_unreachable_daemon_falls_back_and_closes_client(mock_from_env):
    client = MagicMock()
    client.ping.side_effect = docker.errors.DockerException("daemon down")
    mock_from_env.return_value = client

    assert get_docker_client() is None
    assert isinstance(create_workspace(1), SubprocessWorkspace)
    assert client.close.called
    assert workspace._docker_client is None


@patch("docker.from_env")
def test_dead_cached_client_is_replaced(mock_from_env):
    stale, fresh = MagicMock(), MagicMock()
    mock_from_env.side_effect = [stale, fresh]

    assert get_docker_client() is stale
    stale.ping.side_effect = docker.errors.DockerException("connection reset")
    assert get_docker_client() is fresh
    assert stale.close.called


# --- Container teardown ---

def test_cleanup_removes_container_when_stop_fails():
    container = MagicMock()
    container.stop.side_effect = docker.errors.APIError("stop failed")
    ws = DockerWorkspace(task_id=1, client=MagicMock())
    ws.container = container

    ws.cleanup()

    container.remove.assert_called_once_with(force=True)
    assert ws.container is None


def test_cleanup_tolerates_already_removed_container():
    container = MagicMock()
    container.remove.side_effect = docker.errors.NotFound("gone")
    ws = DockerWorkspace(task_id=1, client=MagicMock())
    ws.container = container

    ws.cleanup()  # must not raise
    assert ws.container is None


def test_setup_labels_container_for_reaping():
    client = MagicMock()
    ws = DockerWorkspace(task_id=77, client=client)
    ws.execute_command = MagicMock(return_value=(0, ""))

    ws.setup()

    labels = client.containers.run.call_args.kwargs["labels"]
    assert labels["nimbus.managed"] == "true"
    assert labels["nimbus.task_id"] == "77"
    assert abs(int(labels["nimbus.created"]) - time.time()) < 60


def test_reaper_removes_only_expired_containers():
    now = int(time.time())
    expired = MagicMock(labels={"nimbus.created": str(now - 10_000)})
    live = MagicMock(labels={"nimbus.created": str(now - 60)})
    client = MagicMock()
    client.containers.list.return_value = [expired, live]

    removed = reap_orphaned_containers(client, max_age_seconds=3600)

    assert removed == 1
    expired.remove.assert_called_once_with(force=True)
    assert not live.remove.called
    assert client.containers.list.call_args.kwargs["filters"] == {"label": "nimbus.managed=true"}


# --- Subprocess timeouts ---

def test_subprocess_timeout_kills_child_processes(tmp_path):
    pid_file = tmp_path / "child.pid"
    ws = SubprocessWorkspace(task_id=1)

    code, out = ws.execute_command(
        f"sleep 60 & echo $! > {pid_file}; wait", workdir=str(tmp_path), timeout=1
    )

    assert code == 124
    child_pid = int(pid_file.read_text())
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


# --- Worker task lifecycle ---

def _worker_db(task):
    db = AsyncMock()
    db.get = AsyncMock(return_value=task)
    db.add = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock())  # SQLAlchemy results are sync objects
    return db


@pytest.mark.asyncio
async def test_failed_setup_fails_task_without_running_agent():
    from app.worker import run_agent_loop

    task = Task(id=5, prompt="p", status=TaskStatus.PENDING)
    ws = MagicMock()
    ws.asetup = AsyncMock(return_value=(128, "Failed to set up workspace"))
    ws.acleanup = AsyncMock()

    with patch("app.worker.settings.GEMINI_API_KEY", "k"), \
         patch("app.worker.async_session") as mock_session_ctx, \
         patch("app.worker.UnifiedWorkspace", return_value=ws), \
         patch("app.worker.LLMChatSession") as mock_llm, \
         patch("app.worker.log_event", new_callable=AsyncMock):
        mock_session_ctx.return_value.__aenter__.return_value = _worker_db(task)
        await run_agent_loop(ctx={}, task_id=5, prompt="p")

    assert task.status == TaskStatus.FAILED
    assert not mock_llm.called
    assert ws.acleanup.awaited


@pytest.mark.asyncio
async def test_task_time_limit_fails_task_and_cleans_up():
    from app.worker import run_agent_loop

    async def hang(*args, **kwargs):
        await asyncio.sleep(30)

    task = Task(id=6, prompt="p", status=TaskStatus.PENDING)
    ws = MagicMock()
    ws.asetup = AsyncMock(side_effect=hang)
    ws.acleanup = AsyncMock()

    with patch("app.worker.settings.GEMINI_API_KEY", "k"), \
         patch("app.worker.settings.TASK_TIMEOUT_SECONDS", 0.2), \
         patch("app.worker.async_session") as mock_session_ctx, \
         patch("app.worker.UnifiedWorkspace", return_value=ws), \
         patch("app.worker.log_event", new_callable=AsyncMock) as mock_log:
        mock_session_ctx.return_value.__aenter__.return_value = _worker_db(task)
        await asyncio.wait_for(run_agent_loop(ctx={}, task_id=6, prompt="p"), timeout=5)

    assert task.status == TaskStatus.FAILED
    assert ws.acleanup.awaited
    messages = [c.args[3].get("message", "") for c in mock_log.call_args_list]
    assert any("time limit" in m for m in messages)


def test_worker_settings_backstop_timeout_and_no_retries():
    from app.worker import WorkerSettings
    from app.settings import settings

    assert WorkerSettings.job_timeout > settings.TASK_TIMEOUT_SECONDS
    assert WorkerSettings.max_tries == 1
    assert any(c.name == "cron:reap_orphaned_workspaces" for c in WorkerSettings.cron_jobs)
