import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from urllib.parse import urlparse, parse_qs
import httpx
from httpx import ASGITransport

from app.main import app
from app.models import User, Task, TaskStatus
from app.security import encrypt_secret, internal_api_token
from app.db import get_db


@pytest.fixture
def mock_db():
    db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_test_user_header_does_not_authenticate(mock_db):
    """X-Test-User-Id must not impersonate a user, with or without OAuth configured."""
    mock_db.get = AsyncMock(return_value=User(id=7, github_id="7", username="victim"))

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        for client_id in (None, "oauth-client-id"):
            with patch("app.auth.settings.GITHUB_CLIENT_ID", client_id):
                response = await ac.get("/api/auth/me", headers={"X-Test-User-Id": "7"})
                assert response.status_code == 401


@pytest.mark.asyncio
async def test_internal_events_endpoint_requires_token():
    transport = ASGITransport(app=app)
    payload = {"type": "log", "payload": "{}", "timestamp": ""}
    with patch("app.main.manager.broadcast_event", new_callable=AsyncMock) as mock_broadcast:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            missing = await ac.post("/api/internal/tasks/1/events", json=payload)
            wrong = await ac.post(
                "/api/internal/tasks/1/events",
                json=payload,
                headers={"X-Nimbus-Internal-Token": "forged"}
            )
            assert missing.status_code == 401
            assert wrong.status_code == 401
            assert not mock_broadcast.called

            ok = await ac.post(
                "/api/internal/tasks/1/events",
                json=payload,
                headers={"X-Nimbus-Internal-Token": internal_api_token()}
            )
            assert ok.status_code == 200
            mock_broadcast.assert_awaited_once_with(1, payload)


@pytest.mark.asyncio
async def test_worker_log_event_sends_internal_token():
    from app.worker import log_event
    from app.models import EventType

    db = AsyncMock()
    db.add = MagicMock()
    with patch("app.worker.event_bus.publish_event", new_callable=AsyncMock), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        await log_event(db, 1, EventType.LOG, {"message": "hi"})
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["X-Nimbus-Internal-Token"] == internal_api_token()


@pytest.mark.asyncio
async def test_anonymous_task_list_only_returns_unowned_tasks(mock_db):
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=result)

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/tasks")
        assert response.status_code == 200

    query = str(mock_db.execute.call_args.args[0])
    assert "tasks.user_id IS NULL" in query


@pytest.mark.asyncio
async def test_anonymous_clear_all_tasks_is_rejected(mock_db):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.delete("/api/tasks")
        assert response.status_code == 401

    assert not mock_db.execute.called
    assert not mock_db.commit.called


@pytest.mark.asyncio
async def test_worker_decrypts_user_credentials():
    """Regression: worker.py used decrypt_secret without importing it (NameError for logged-in users)."""
    from app.worker import run_agent_loop

    task = Task(id=3, user_id=1, prompt="p", status=TaskStatus.PENDING)
    user = User(id=1, github_id="1", username="dev", github_token=encrypt_secret("ghp_x"))
    db = AsyncMock()
    db.get = AsyncMock(side_effect=[task, user])
    creds = MagicMock()
    creds.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=creds)

    with patch("app.worker.settings.GEMINI_API_KEY", None), \
         patch("app.worker.settings.GROQ_API_KEY", None), \
         patch("app.worker.settings.OPENROUTER_API_KEY", None), \
         patch("app.worker.async_session") as mock_session_ctx, \
         patch("app.worker.log_event", new_callable=AsyncMock):
        mock_session_ctx.return_value.__aenter__.return_value = db
        await run_agent_loop(ctx={}, task_id=3, prompt="p")

    assert task.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_oauth_login_sets_state_cookie():
    transport = ASGITransport(app=app)
    with patch("app.auth.settings.GITHUB_CLIENT_ID", "cid"):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/auth/github/login")

    assert response.status_code in (302, 307)
    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    assert response.cookies.get("nimbus_oauth_state") == state


@pytest.mark.asyncio
async def test_oauth_callback_rejects_missing_or_mismatched_state(mock_db):
    transport = ASGITransport(app=app)
    with patch("app.auth.settings.GITHUB_CLIENT_ID", "cid"), \
         patch("app.auth.settings.GITHUB_CLIENT_SECRET", "secret"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            no_cookie = await ac.get("/api/auth/github/callback", params={"code": "c", "state": "abc"})
            ac.cookies.set("nimbus_oauth_state", "expected")
            mismatch = await ac.get("/api/auth/github/callback", params={"code": "c", "state": "abc"})
            no_state = await ac.get("/api/auth/github/callback", params={"code": "c"})

    assert no_cookie.status_code == 400
    assert mismatch.status_code == 400
    assert no_state.status_code == 400
    assert not mock_post.called
