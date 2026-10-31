"""Auth through the frontend's /api proxy: first-party cookies, OAuth callback origin, stream tickets."""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport
from starlette.websockets import WebSocketDisconnect

from app.db import get_db
from app.main import app
from app.models import Task, TaskStatus, User
from app.security import create_access_token, create_stream_ticket, verify_stream_ticket
from app.settings import cookie_secure
from tests.test_websocket_stream import _event, _session_factory

OWNER = User(id=7, github_id="7", username="owner", onboarding_completed=True)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.clear()


def session_cookie(user_id=7):
    return create_access_token({"sub": str(user_id)})


def client():
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# --- Cookies and OAuth ---

def test_cookie_secure_follows_frontend_scheme_unless_overridden():
    with patch("app.settings.settings.COOKIE_SECURE", None):
        with patch("app.settings.settings.FRONTEND_URL", "https://nimbusagent.vercel.app"):
            assert cookie_secure() is True
        with patch("app.settings.settings.FRONTEND_URL", "http://localhost:3000"):
            assert cookie_secure() is False
    with patch("app.settings.settings.COOKIE_SECURE", False), \
         patch("app.settings.settings.FRONTEND_URL", "https://nimbusagent.vercel.app"):
        assert cookie_secure() is False


@pytest.mark.asyncio
async def test_oauth_login_returns_to_configured_origin_with_secure_state_cookie():
    with patch("app.auth.settings.GITHUB_CLIENT_ID", "cid"), \
         patch("app.auth.settings.OAUTH_REDIRECT_BASE_URL", "https://nimbusagent.vercel.app/"), \
         patch("app.settings.settings.COOKIE_SECURE", True):
        async with client() as ac:
            response = await ac.get("/api/auth/github/login")

    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["redirect_uri"] == ["https://nimbusagent.vercel.app/api/auth/github/callback"]
    assert query["scope"] == ["read:user,user:email,repo"]
    state_cookie = response.headers["set-cookie"]
    assert "nimbus_oauth_state=" in state_cookie and "Secure" in state_cookie


@pytest.mark.asyncio
async def test_oauth_login_defaults_to_api_origin():
    with patch("app.auth.settings.GITHUB_CLIENT_ID", "cid"), \
         patch("app.auth.settings.OAUTH_REDIRECT_BASE_URL", None):
        async with client() as ac:
            response = await ac.get("/api/auth/github/login")
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["redirect_uri"] == ["http://test/api/auth/github/callback"]


@pytest.mark.asyncio
async def test_oauth_callback_sets_secure_first_party_session(mock_db):
    token_resp = MagicMock(status_code=200)
    token_resp.json.return_value = {"access_token": "gho_x"}
    profile_resp = MagicMock(status_code=200)
    profile_resp.json.return_value = {"id": 7, "login": "owner", "email": "o@example.com"}
    result = MagicMock()
    result.scalar_one_or_none.return_value = User(id=7, github_id="7", username="owner", onboarding_completed=True)
    mock_db.execute = AsyncMock(return_value=result)
    mock_db.add = MagicMock()

    with patch("app.auth.settings.GITHUB_CLIENT_ID", "cid"), \
         patch("app.auth.settings.GITHUB_CLIENT_SECRET", "secret"), \
         patch("app.auth.settings.FRONTEND_URL", "https://nimbusagent.vercel.app"), \
         patch("app.settings.settings.COOKIE_SECURE", None), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=token_resp), \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=profile_resp):
        async with client() as ac:
            ac.cookies.set("nimbus_oauth_state", "s")
            # ac.request, not ac.get: AsyncClient.get is patched to fake GitHub
            response = await ac.request("GET", "/api/auth/github/callback", params={"code": "c", "state": "s"})

    assert response.status_code == 302
    assert response.headers["location"] == "https://nimbusagent.vercel.app/"
    session = next(c for c in response.headers.get_list("set-cookie") if c.startswith("nimbus_session="))
    assert "HttpOnly" in session and "Secure" in session and "samesite=lax" in session.lower()


@pytest.mark.asyncio
async def test_logout_clears_cookie_with_matching_attributes():
    with patch("app.settings.settings.COOKIE_SECURE", True):
        async with client() as ac:
            response = await ac.post("/api/auth/logout")
    cleared = response.headers["set-cookie"]
    assert cleared.startswith('nimbus_session=""') and "Secure" in cleared and "Max-Age=0" in cleared


# --- Stream tickets ---

def test_stream_ticket_is_scoped_to_one_task_and_expires():
    ticket = create_stream_ticket(7, 1)
    assert verify_stream_ticket(ticket, 1) == "7"
    assert verify_stream_ticket(ticket, 2) is None
    assert verify_stream_ticket(session_cookie(), 1) is None  # a session is not a ticket
    assert verify_stream_ticket(None, 1) is None

    with patch("app.security.STREAM_TICKET_TTL", datetime.timedelta(seconds=-1)):
        from app import security
        expired = security.create_stream_ticket(7, 1)
    assert verify_stream_ticket(expired, 1) is None


@pytest.mark.asyncio
async def test_stream_ticket_is_not_accepted_as_a_session(mock_db):
    mock_db.get = AsyncMock(return_value=OWNER)
    ticket = create_stream_ticket(7, 1)
    async with client() as ac:
        as_bearer = await ac.get("/api/auth/me", headers={"Authorization": f"Bearer {ticket}"})
        ac.cookies.set("nimbus_session", ticket)
        as_cookie = await ac.get("/api/auth/me")
    assert as_bearer.status_code == 401
    assert as_cookie.status_code == 401


@pytest.mark.asyncio
async def test_ticket_endpoint_only_issues_to_the_owner(mock_db):
    owned = Task(id=1, user_id=7, prompt="p", status=TaskStatus.RUNNING)
    anonymous = Task(id=2, user_id=None, prompt="p", status=TaskStatus.RUNNING)

    async def get(model, key):
        if model is User:
            return User(id=key, github_id=str(key), username=f"u{key}")
        return {1: owned, 2: anonymous}.get(key)

    mock_db.get = AsyncMock(side_effect=get)
    async with client() as ac:
        nobody = await ac.post("/api/tasks/1/stream-ticket")
        ac.cookies.set("nimbus_session", session_cookie(8))
        stranger = await ac.post("/api/tasks/1/stream-ticket")
        missing = await ac.post("/api/tasks/99/stream-ticket")
        ac.cookies.set("nimbus_session", session_cookie(7))
        owner = await ac.post("/api/tasks/1/stream-ticket")
        anon = await ac.post("/api/tasks/2/stream-ticket")

    assert nobody.status_code == stranger.status_code == missing.status_code == 404
    assert owner.status_code == 200
    assert verify_stream_ticket(owner.json()["ticket"], 1) == "7"
    assert owner.json()["expires_in"] == 60
    assert anon.json()["ticket"] is None


def _ws_close_code(url, task, cookies=None):
    factory, _ = _session_factory(task, [_event(1, "hello")])
    with patch("app.main.async_session", factory):
        test_client = TestClient(app, cookies=cookies)
        with test_client.websocket_connect(url) as ws:
            try:
                return ws.receive_json()
            except WebSocketDisconnect as exc:
                return exc.code


def test_websocket_accepts_ticket_for_owned_task():
    task = Task(id=1, user_id=7, prompt="p", status=TaskStatus.RUNNING)
    message = _ws_close_code(f"/ws/tasks/1?ticket={create_stream_ticket(7, 1)}", task)
    assert message["id"] == 1


@pytest.mark.parametrize("ticket", [
    lambda: create_stream_ticket(7, 2),   # another task's ticket
    lambda: create_stream_ticket(8, 1),   # someone else's ticket
    lambda: session_cookie(7),            # a session token in the URL is no longer accepted
    lambda: "garbage",
])
def test_websocket_rejects_wrong_tickets(ticket):
    task = Task(id=1, user_id=7, prompt="p", status=TaskStatus.RUNNING)
    assert _ws_close_code(f"/ws/tasks/1?ticket={ticket()}", task) == 1008


def test_websocket_still_accepts_same_origin_session_cookie():
    task = Task(id=1, user_id=7, prompt="p", status=TaskStatus.RUNNING)
    assert _ws_close_code("/ws/tasks/1", task, cookies={"nimbus_session": session_cookie(7)})["id"] == 1
    # ...but not a ticket smuggled in as the cookie
    ticket_cookie = {"nimbus_session": create_stream_ticket(7, 1)}
    assert _ws_close_code("/ws/tasks/1", task, cookies=ticket_cookie) == 1008
