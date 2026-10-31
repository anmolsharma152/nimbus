"""Follow-ups continue the same task, branch and PR instead of creating a new task."""

import datetime
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agent import initial_prompt
from app.auth import get_optional_user
from app.db import Base, get_db
from app.github_client import RepoAccess
from app.main import app
from app.models import Task, TaskEvent, TaskMessage, TaskStatus, User
from app.ratelimit import _hourly_runs

BASE = "b" * 40
PUSHED = "c" * 40
NEW = "d" * 40


@pytest.fixture
def api():
    """Yields (db mock, set_task) with the task lookup returning whatever set_task stored."""
    db = AsyncMock()
    db.add = MagicMock()
    holder = {}

    async def execute(stmt, *a, **k):
        result = MagicMock()
        result.scalar_one_or_none.return_value = holder.get("task")
        result.scalar.return_value = 0
        return result
    db.execute = AsyncMock(side_effect=execute)
    app.dependency_overrides[get_db] = lambda: db
    yield db, lambda t: holder.__setitem__("task", t)
    app.dependency_overrides.clear()


def _sign_in(user_id=1):
    app.dependency_overrides[get_optional_user] = lambda: User(id=user_id, username="dev", tier="free")


async def _post(path, json=None):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.post(path, json=json)


def _done_task(**kw):
    defaults = dict(
        id=21, user_id=1, prompt="Add a /health route", repo_url="https://github.com/org/proj",
        git_branch="nimbus/task-21", status=TaskStatus.COMPLETED, patch_diff="diff --git a/x b/x\n",
        base_sha=BASE, pushed_sha=PUSHED, head_repo="org/proj", pr_url="https://github.com/org/proj/pull/3",
    )
    defaults.update(kw)
    return Task(**defaults)


# --- API ---

@pytest.mark.asyncio
async def test_follow_up_requeues_the_same_task(api):
    db, set_task = api
    task = _done_task()
    set_task(task)
    _sign_in()
    with patch("app.main.enqueue_task", new_callable=AsyncMock) as enqueue:
        resp = await _post("/api/tasks/21/messages", {"message": "  Also add a test  "})

    assert resp.status_code == 200 and resp.json()["id"] == 21
    assert task.status == TaskStatus.PENDING
    added = [c.args[0] for c in db.add.call_args_list]
    message = next(a for a in added if isinstance(a, TaskMessage))
    assert (message.task_id, message.content) == (21, "Also add a test")
    marker = next(a for a in added if isinstance(a, TaskEvent))
    assert json.loads(marker.payload) == {
        "message": "💬 Follow-up: Also add a test", "turn": "follow_up", "text": "Also add a test"
    }
    # State the follow-up builds on is kept
    assert task.patch_diff and task.base_sha == BASE and task.pushed_sha == PUSHED and task.pr_url
    enqueue.assert_awaited_once_with(21, task.prompt, task.repo_url, "nimbus/task-21")


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [TaskStatus.PENDING, TaskStatus.RUNNING])
async def test_follow_up_rejected_while_task_is_active(api, state):
    _, set_task = api
    set_task(_done_task(status=state))
    _sign_in()
    with patch("app.main.enqueue_task", new_callable=AsyncMock) as enqueue:
        resp = await _post("/api/tasks/21/messages", {"message": "more"})
    assert resp.status_code == 409 and not enqueue.called


@pytest.mark.asyncio
async def test_empty_follow_up_rejected(api):
    _, set_task = api
    set_task(_done_task())
    _sign_in()
    resp = await _post("/api/tasks/21/messages", {"message": "   "})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_follow_up_on_someone_elses_task_is_not_found(api):
    _, set_task = api
    set_task(_done_task(user_id=2))
    _sign_in(user_id=1)
    resp = await _post("/api/tasks/21/messages", {"message": "more"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_follow_up_on_legacy_anonymous_repo_task_needs_sign_in(api):
    _, set_task = api
    set_task(_done_task(user_id=None))
    resp = await _post("/api/tasks/21/messages", {"message": "more"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_follow_up_counts_against_rate_limit(api):
    _, set_task = api
    set_task(_done_task())
    _sign_in()
    from fastapi import HTTPException
    with patch("app.main.check_task_submission_limits", new_callable=AsyncMock,
               side_effect=HTTPException(status_code=429, detail="limit")), \
         patch("app.main.enqueue_task", new_callable=AsyncMock) as enqueue:
        resp = await _post("/api/tasks/21/messages", {"message": "more"})
    assert resp.status_code == 429 and not enqueue.called


@pytest.mark.asyncio
async def test_retry_starts_over_but_keeps_branch_and_pr(api):
    db, set_task = api
    task = _done_task(status=TaskStatus.FAILED)
    set_task(task)
    _sign_in()
    with patch("app.main.enqueue_task", new_callable=AsyncMock):
        resp = await _post("/api/tasks/21/retry")
    assert resp.status_code == 200
    assert task.patch_diff is None and task.base_sha is None
    assert task.pushed_sha == PUSHED and task.pr_url and task.head_repo == "org/proj"
    marker = next(c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], TaskEvent))
    assert json.loads(marker.payload)["turn"] == "retry"


def test_hourly_limit_counts_tasks_and_follow_ups():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    old = now - datetime.timedelta(hours=2)
    with Session(engine) as s:
        s.add_all([User(id=1, github_id="1", username="a"), User(id=2, github_id="2", username="b")])
        s.add_all([
            Task(id=1, user_id=1, prompt="p", created_at=old),
            Task(id=2, user_id=1, prompt="p", created_at=now),
            Task(id=3, user_id=2, prompt="p", created_at=now),
        ])
        s.add_all([
            TaskMessage(task_id=1, content="m", created_at=now),
            TaskMessage(task_id=1, content="m", created_at=now),
            TaskMessage(task_id=1, content="m", created_at=old),
            TaskMessage(task_id=3, content="m", created_at=now),
        ])
        s.commit()
        since = now - datetime.timedelta(hours=1)
        # user 1: one recent task + two recent follow-ups (the old task's age doesn't matter)
        assert s.execute(_hourly_runs(Task.user_id == 1, since)).scalar() == 3
        assert s.execute(_hourly_runs(Task.user_id == 2, since)).scalar() == 2
        assert s.execute(_hourly_runs(Task.user_id.is_(None), since)).scalar() == 0
    engine.dispose()


# --- prompt ---

def test_prompt_for_follow_up_names_latest_instruction():
    text = initial_prompt("Goal", "https://github.com/o/r", "b", follow_ups=["first", "second"], continuing=True)
    assert "Earlier follow-up 1:\nfirst" in text
    assert "Latest follow-up (do this now):\nsecond" in text
    assert "already in the working tree" in text


def test_prompt_when_earlier_changes_were_lost_or_retried():
    lost = initial_prompt("Goal", None, "b", follow_ups=["x"], continuing=False)
    assert "could not be restored" in lost
    fresh = initial_prompt("Goal", None, "b", follow_ups=["x"])
    assert "could not be restored" not in fresh and "clean checkout" in fresh
    assert "follow-up" not in initial_prompt("Goal", None, "b").lower()


# --- worker ---

@pytest.mark.asyncio
async def test_worker_rebuilds_task_state_for_follow_up():
    from app.worker import run_agent_loop

    task = _done_task(status=TaskStatus.PENDING)
    user = User(id=1, github_id="1", username="dev", github_token="enc")
    db = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock(side_effect=[task, user])
    creds = MagicMock()
    creds.scalars.return_value.all.return_value = []
    msgs = MagicMock()
    msgs.scalars.return_value.all.return_value = ["Also add a test"]
    db.execute = AsyncMock(side_effect=[creds, msgs])

    ws = MagicMock()
    ws.base_sha = BASE
    ws.asetup = AsyncMock(return_value=(0, ""))
    ws.aapply_patch = AsyncMock(return_value=(0, ""))
    ws.aexecute_command = AsyncMock(return_value=(0, ""))
    ws.acleanup = AsyncMock()
    seen = {}

    async def fake_agent(llm, workspace, first_prompt, *a, **k):
        seen["prompt"] = first_prompt
        return "cancelled"

    with patch("app.worker.settings.GEMINI_API_KEY", "k"), \
         patch("app.worker.decrypt_secret", return_value="tok"), \
         patch("app.worker.async_session") as session_ctx, \
         patch("app.worker.UnifiedWorkspace", return_value=ws), \
         patch("app.worker.get_repo_access", new_callable=AsyncMock,
               return_value=(RepoAccess("org/proj", "main", True, True), None)), \
         patch("app.worker.LLMChatSession"), \
         patch("app.worker.run_agent_commands", side_effect=fake_agent), \
         patch("app.worker.log_event", new_callable=AsyncMock):
        session_ctx.return_value.__aenter__.return_value = db
        await run_agent_loop(ctx={}, task_id=21, prompt=task.prompt, repo_url=task.repo_url, git_branch=task.git_branch)

    assert ws.asetup.await_args.kwargs["start_point"] == BASE
    assert ws.asetup.await_args.kwargs["branch_name"] == "nimbus/task-21"
    ws.aapply_patch.assert_awaited_once_with("diff --git a/x b/x\n")
    assert "Latest follow-up (do this now):\nAlso add a test" in seen["prompt"]
    assert "already in the working tree" in seen["prompt"]


@pytest.mark.asyncio
async def test_deliver_follow_up_updates_same_branch_and_pr():
    from app.worker import _deliver_changes

    task = _done_task(head_repo="dev/proj")  # earlier run pushed to the user's fork
    ws = MagicMock()
    ws.apush_branch = AsyncMock(return_value=(0, NEW))
    with patch("app.worker.ensure_fork", new_callable=AsyncMock) as fork, \
         patch("app.worker.create_draft_pr", new_callable=AsyncMock) as pr, \
         patch("app.worker.log_event", new_callable=AsyncMock) as log_event:
        await _deliver_changes(
            AsyncMock(), task, ws, task.repo_url, RepoAccess("org/proj", "main", False, True),
            "tok", "nimbus/task-21", "p", "diff", "Dev", "d@x", "@dev", {}
        )
    kwargs = ws.apush_branch.await_args.kwargs
    assert kwargs["expect_sha"] == PUSHED
    assert kwargs["push_url"] == "https://github.com/dev/proj.git"
    assert not fork.called and not pr.called
    assert task.pushed_sha == NEW and task.head_repo == "dev/proj"
    assert "Updated draft PR" in log_event.await_args.args[3]["message"]


@pytest.mark.asyncio
async def test_first_delivery_records_pushed_commit():
    from app.worker import _deliver_changes

    task = Task(id=22, git_branch="nimbus/task-22")
    ws = MagicMock()
    ws.apush_branch = AsyncMock(return_value=(0, NEW))
    with patch("app.worker.create_draft_pr", new_callable=AsyncMock, return_value="https://pr"), \
         patch("app.worker.log_event", new_callable=AsyncMock):
        await _deliver_changes(
            AsyncMock(), task, ws, "https://github.com/org/proj", RepoAccess("org/proj", "main", True, True),
            "tok", "nimbus/task-22", "p", "diff", "Dev", "d@x", "@dev", {}
        )
    assert ws.apush_branch.await_args.kwargs["expect_sha"] is None
    assert (task.pushed_sha, task.head_repo, task.pr_url) == (NEW, "org/proj", "https://pr")
