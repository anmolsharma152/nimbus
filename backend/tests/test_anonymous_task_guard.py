"""Anonymous tasks never touch GitHub with server credentials and cannot pick protected branches."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from httpx import ASGITransport

from app.auth import get_optional_user
from app.branches import validate_task_branch
from app.db import get_db
from app.main import app
from app.models import Task, TaskStatus, User
from app.ratelimit import check_task_submission_limits
from app.settings import Settings


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()

    async def refresh(t):
        t.id = 1
    db.refresh = AsyncMock(side_effect=refresh)
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.clear()


async def _post(path, json=None):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.post(path, json=json)


@pytest.mark.parametrize("name", ["nimbus/task-1", "fix-login", "feature/auth.v2", "user_x/fix-3"])
def test_allowed_branch_names(name):
    assert validate_task_branch(name) == name


@pytest.mark.parametrize("name", [
    "main", "MASTER", "develop", "gh-pages", "HEAD", "release/1.0", "hotfix/x", "refs/heads/main",
    "a..b", "-rf", "bad name", "x.lock", "trailing/", "a//b", "dir/.hidden", "x" * 101, "$(id)",
])
def test_rejected_branch_names(name):
    with pytest.raises(ValueError):
        validate_task_branch(name)


def test_blank_branch_means_default():
    assert validate_task_branch(None) is None
    assert validate_task_branch("  ") is None


def test_server_github_token_setting_is_gone():
    assert "GITHUB_TOKEN" not in Settings.model_fields


@pytest.mark.asyncio
async def test_anonymous_repo_task_requires_sign_in(mock_db):
    with patch("app.main.enqueue_task", new_callable=AsyncMock) as enqueue:
        resp = await _post("/api/tasks", {"prompt": "p", "repo_url": "https://github.com/o/r"})
    assert resp.status_code == 401
    assert not mock_db.add.called
    assert not enqueue.called


@pytest.mark.asyncio
async def test_anonymous_task_without_repo_is_allowed(mock_db):
    with patch("app.main.enqueue_task", new_callable=AsyncMock) as enqueue, \
         patch("app.main.check_task_submission_limits", new_callable=AsyncMock) as limits:
        resp = await _post("/api/tasks", {"prompt": "p", "repo_url": "  "})
    assert resp.status_code == 200
    assert resp.json()["repo_url"] is None
    limits.assert_awaited_once()
    assert enqueue.called


@pytest.mark.asyncio
async def test_protected_branch_is_rejected_even_when_signed_in(mock_db):
    app.dependency_overrides[get_optional_user] = lambda: User(id=1, username="dev", tier="free")
    with patch("app.main.enqueue_task", new_callable=AsyncMock) as enqueue:
        resp = await _post(
            "/api/tasks", {"prompt": "p", "repo_url": "https://github.com/o/r", "git_branch": "main"}
        )
    assert resp.status_code == 422
    assert not enqueue.called


@pytest.mark.asyncio
async def test_retry_of_legacy_anonymous_repo_task_is_rejected(mock_db):
    task = Task(id=9, prompt="p", repo_url="https://github.com/o/r", status=TaskStatus.FAILED)
    result = MagicMock()
    result.scalar_one_or_none.return_value = task
    mock_db.execute.return_value = result
    with patch("app.main.enqueue_task", new_callable=AsyncMock) as enqueue:
        resp = await _post("/api/tasks/9/retry")
    assert resp.status_code == 401
    assert task.status == TaskStatus.FAILED
    assert not enqueue.called


def _count(n):
    res = MagicMock()
    res.scalar.return_value = n
    return res


@pytest.mark.asyncio
async def test_anonymous_hourly_limit():
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_count(0), _count(10)])
    with patch("app.ratelimit.settings.ANON_TASKS_PER_HOUR", 10):
        with pytest.raises(HTTPException) as exc:
            await check_task_submission_limits(None, db)
    assert exc.value.status_code == 429
    assert "hourly" in exc.value.detail


@pytest.mark.asyncio
async def test_anonymous_under_hourly_limit_passes():
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_count(0), _count(9)])
    with patch("app.ratelimit.settings.ANON_TASKS_PER_HOUR", 10):
        await check_task_submission_limits(None, db)


async def _run_worker(task, user, repo_url, git_branch):
    from app.worker import run_agent_loop

    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, user])
    creds = MagicMock()
    creds.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=creds)
    with patch("app.worker.async_session") as session_ctx, \
         patch("app.worker.log_event", new_callable=AsyncMock) as log_event, \
         patch("app.worker.UnifiedWorkspace") as workspace_cls:
        session_ctx.return_value.__aenter__.return_value = db
        workspace_cls.return_value.asetup = AsyncMock(return_value=(1, "stop"))
        workspace_cls.return_value.acleanup = AsyncMock()
        await run_agent_loop(ctx={}, task_id=task.id, prompt="p", repo_url=repo_url, git_branch=git_branch)
    return workspace_cls.return_value, log_event


@pytest.mark.asyncio
async def test_worker_refuses_queued_anonymous_repo_task():
    task = Task(id=5, user_id=None, prompt="p", status=TaskStatus.PENDING)
    ws, log_event = await _run_worker(task, None, "https://github.com/o/r", None)
    assert task.status == TaskStatus.FAILED
    assert not ws.asetup.called
    messages = [c.args[3].get("message", "") for c in log_event.await_args_list]
    assert any("Sign in" in m for m in messages)


@pytest.mark.asyncio
async def test_worker_refuses_queued_protected_branch():
    task = Task(id=6, user_id=1, prompt="p", status=TaskStatus.PENDING)
    user = User(id=1, github_id="1", username="dev")
    ws, _ = await _run_worker(task, user, "https://github.com/o/r", "master")
    assert task.status == TaskStatus.FAILED
    assert not ws.asetup.called
