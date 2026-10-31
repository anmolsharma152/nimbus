"""Repo access is checked as the task owner; PRs target the default branch; no write access -> fork."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app import github_client
from app.github_client import RepoAccess, create_draft_pr, ensure_fork, get_repo_access
from app.models import Task, TaskStatus, User

TOKEN = "test-canary-repo-permissions-token"
_RealAsyncClient = httpx.AsyncClient


def _mock_github(handler):
    """Routes github_client's httpx calls to `handler(request) -> httpx.Response`; records requests."""
    seen = []

    def wrapped(request):
        seen.append(request)
        return handler(request)

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return _RealAsyncClient(*args, transport=httpx.MockTransport(wrapped), **kwargs)

    return patch.object(github_client.httpx, "AsyncClient", side_effect=factory), seen


def _repo_json(push=True, default_branch="trunk", allow_forking=True):
    return {
        "full_name": "org/proj",
        "default_branch": default_branch,
        "allow_forking": allow_forking,
        "permissions": {"pull": True, "push": push},
    }


# --- get_repo_access ---

@pytest.mark.asyncio
async def test_repo_access_reads_push_permission_and_default_branch():
    mock, seen = _mock_github(lambda r: httpx.Response(200, json=_repo_json(push=True)))
    with mock:
        access, error = await get_repo_access("https://github.com/org/proj", TOKEN)
    assert error is None
    assert access == RepoAccess("org/proj", "trunk", can_push=True, allow_forking=True)
    assert seen[0].url.path == "/repos/org/proj"
    assert seen[0].headers["Authorization"] == f"Bearer {TOKEN}"


@pytest.mark.asyncio
async def test_repo_access_without_push_permission():
    mock, _ = _mock_github(lambda r: httpx.Response(200, json=_repo_json(push=False)))
    with mock:
        access, error = await get_repo_access("org/proj", TOKEN)
    assert error is None and access.can_push is False


@pytest.mark.asyncio
async def test_repo_access_without_token_never_claims_push():
    mock, seen = _mock_github(lambda r: httpx.Response(200, json=_repo_json(push=True)))
    with mock:
        access, _ = await get_repo_access("org/proj", None)
    assert access.can_push is False
    assert "Authorization" not in seen[0].headers


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [401, 403, 404])
async def test_repo_access_denied(code):
    mock, _ = _mock_github(lambda r: httpx.Response(code, json={}))
    with mock:
        access, error = await get_repo_access("org/proj", TOKEN)
    assert access is None
    assert "not found or your GitHub account cannot access it" in error
    assert TOKEN not in error


@pytest.mark.asyncio
async def test_repo_access_network_error():
    def boom(request):
        raise httpx.ConnectError("down")
    mock, _ = _mock_github(boom)
    with mock:
        access, error = await get_repo_access("org/proj", TOKEN)
    assert access is None and "Could not reach GitHub" in error


# --- ensure_fork ---

@pytest.mark.asyncio
async def test_fork_waits_until_branches_are_copied():
    calls = {"branches": 0}

    def handler(request):
        if request.method == "POST":
            assert request.url.path == "/repos/org/proj/forks"
            assert json.loads(request.content) == {"default_branch_only": True}
            return httpx.Response(202, json={"full_name": "dev/proj"})
        assert request.url.path == "/repos/dev/proj/branches"
        calls["branches"] += 1
        return httpx.Response(200, json=[] if calls["branches"] < 3 else [{"name": "trunk"}])

    mock, _ = _mock_github(handler)
    with mock, patch("app.github_client.asyncio.sleep", new_callable=AsyncMock) as sleep:
        fork, error = await ensure_fork(RepoAccess("org/proj", "trunk", False, True), TOKEN)
    assert (fork, error) == ("dev/proj", None)
    assert calls["branches"] == 3 and sleep.await_count == 2


@pytest.mark.asyncio
async def test_fork_gives_up_after_deadline():
    def handler(request):
        if request.method == "POST":
            return httpx.Response(202, json={"full_name": "dev/proj"})
        return httpx.Response(404, json={})

    mock, _ = _mock_github(handler)
    with mock, patch("app.github_client.asyncio.sleep", new_callable=AsyncMock):
        fork, error = await ensure_fork(RepoAccess("org/proj", "trunk", False, True), TOKEN, wait_seconds=0)
    assert fork is None and "not ready" in error


@pytest.mark.asyncio
async def test_fork_refused_when_repo_disallows_forking():
    mock, seen = _mock_github(lambda r: httpx.Response(500))
    with mock:
        fork, error = await ensure_fork(RepoAccess("org/proj", "trunk", False, False), TOKEN)
    assert fork is None and "does not allow forking" in error
    assert not seen


# --- create_draft_pr ---

@pytest.mark.asyncio
async def test_pr_targets_given_base_and_fork_head():
    def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/repos/org/proj/pulls"
        assert body["base"] == "trunk" and body["head"] == "dev:nimbus/task-1" and body["draft"] is True
        return httpx.Response(201, json={"html_url": "https://github.com/org/proj/pull/1"})

    mock, _ = _mock_github(handler)
    with mock:
        url = await create_draft_pr("org/proj", "t", "b", "nimbus/task-1", "trunk", TOKEN, head_owner="dev")
    assert url == "https://github.com/org/proj/pull/1"


@pytest.mark.asyncio
async def test_pr_failure_does_not_retry_other_bases():
    mock, seen = _mock_github(lambda r: httpx.Response(422, json={}))
    with mock:
        url = await create_draft_pr("org/proj", "t", "b", "nimbus/task-1", "trunk", TOKEN)
    assert url is None and len(seen) == 1


# --- worker ---

def _worker_db(task, user):
    db = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock(side_effect=[task, user])
    creds = MagicMock()
    creds.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=creds)
    return db


async def _run(access_result, task_id=11):
    from app.worker import run_agent_loop

    task = Task(id=task_id, user_id=1, prompt="p", status=TaskStatus.PENDING)
    user = User(id=1, github_id="1", username="dev", github_token=None)
    ws = MagicMock()
    ws.asetup = AsyncMock(return_value=(1, "stop"))
    ws.acleanup = AsyncMock()
    with patch("app.worker.settings.GEMINI_API_KEY", "k"), \
         patch("app.worker.decrypt_secret", return_value=TOKEN), \
         patch("app.worker.async_session") as session_ctx, \
         patch("app.worker.UnifiedWorkspace", return_value=ws), \
         patch("app.worker.get_repo_access", new_callable=AsyncMock, return_value=access_result) as access, \
         patch("app.worker.log_event", new_callable=AsyncMock) as log_event:
        user.github_token = "encrypted"
        session_ctx.return_value.__aenter__.return_value = _worker_db(task, user)
        await run_agent_loop(ctx={}, task_id=task_id, prompt="p", repo_url="https://github.com/org/proj")
    messages = [c.args[3].get("message", "") for c in log_event.await_args_list]
    return task, ws, access, messages


@pytest.mark.asyncio
async def test_worker_fails_fast_when_repo_is_inaccessible():
    task, ws, access, messages = await _run((None, "Repository org/proj was not found"))
    assert task.status == TaskStatus.FAILED
    assert not ws.asetup.called
    assert access.await_args.args == ("https://github.com/org/proj", TOKEN)
    assert any("was not found" in m for m in messages)


@pytest.mark.asyncio
async def test_worker_fails_fast_without_push_or_fork_option():
    task, ws, _, messages = await _run((RepoAccess("org/proj", "trunk", False, False), None))
    assert task.status == TaskStatus.FAILED
    assert not ws.asetup.called
    assert any("does not allow forking" in m for m in messages)


@pytest.mark.asyncio
async def test_worker_announces_fork_flow_before_running():
    task, ws, _, messages = await _run((RepoAccess("org/proj", "trunk", False, True), None))
    assert ws.asetup.called  # proceeds (setup then fails in this test)
    assert any("pushed to a fork" in m for m in messages)


def _deliver_ws():
    ws = MagicMock()
    ws.apush_branch = AsyncMock(return_value=(0, ""))
    return ws


@pytest.mark.asyncio
async def test_deliver_pushes_upstream_and_targets_default_branch():
    from app.worker import _deliver_changes

    task, ws, stats = Task(id=12), _deliver_ws(), {}
    with patch("app.worker.ensure_fork", new_callable=AsyncMock) as fork, \
         patch("app.worker.create_draft_pr", new_callable=AsyncMock, return_value="https://pr") as pr, \
         patch("app.worker.log_event", new_callable=AsyncMock):
        await _deliver_changes(
            AsyncMock(), task, ws, "https://github.com/org/proj", RepoAccess("org/proj", "trunk", True, True),
            TOKEN, "nimbus/task-12", "p", "diff", "Dev", "d@x", "@dev", stats
        )
    assert not fork.called
    assert ws.apush_branch.await_args.kwargs["push_url"] is None
    assert pr.await_args.kwargs["base_branch"] == "trunk"
    assert pr.await_args.kwargs["head_owner"] is None
    assert task.pr_url == "https://pr" and stats["pr_opened"]


@pytest.mark.asyncio
async def test_deliver_uses_fork_without_write_access():
    from app.worker import _deliver_changes

    task, ws = Task(id=13), _deliver_ws()
    with patch("app.worker.ensure_fork", new_callable=AsyncMock, return_value=("dev/proj", None)), \
         patch("app.worker.create_draft_pr", new_callable=AsyncMock, return_value="https://pr") as pr, \
         patch("app.worker.log_event", new_callable=AsyncMock):
        await _deliver_changes(
            AsyncMock(), task, ws, "https://github.com/org/proj", RepoAccess("org/proj", "trunk", False, True),
            TOKEN, "nimbus/task-13", "p", "diff", "Dev", "d@x", "@dev", {}
        )
    assert ws.apush_branch.await_args.kwargs["push_url"] == "https://github.com/dev/proj.git"
    assert pr.await_args.kwargs["head_owner"] == "dev"
    assert pr.await_args.kwargs["base_branch"] == "trunk"
    assert pr.await_args.kwargs["repo_url"] == "https://github.com/org/proj"


@pytest.mark.asyncio
async def test_deliver_stops_when_fork_fails():
    from app.worker import _deliver_changes

    task, ws = Task(id=14), _deliver_ws()
    with patch("app.worker.ensure_fork", new_callable=AsyncMock, return_value=(None, "Could not fork")), \
         patch("app.worker.create_draft_pr", new_callable=AsyncMock) as pr, \
         patch("app.worker.log_event", new_callable=AsyncMock) as log_event:
        await _deliver_changes(
            AsyncMock(), task, ws, "https://github.com/org/proj", RepoAccess("org/proj", "trunk", False, True),
            TOKEN, "nimbus/task-14", "p", "diff", "Dev", "d@x", "@dev", {}
        )
    assert not ws.apush_branch.called and not pr.called
    assert "Could not fork" in log_event.await_args.args[3]["message"]
