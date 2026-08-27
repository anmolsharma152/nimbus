import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from httpx import ASGITransport
import datetime

from app.main import app
from app.models import User, Task, TaskStatus
from app.security import (
    encrypt_secret,
    decrypt_secret,
    create_access_token,
    decode_access_token
)
from app.db import get_db


def test_encryption_roundtrip():
    """Verify that Fernet encryption and decryption preserves secrets accurately."""
    original_pat = "ghp_superSecretGitHubPersonalAccessToken12345"
    ciphertext = encrypt_secret(original_pat)
    
    assert ciphertext is not None
    assert ciphertext != original_pat
    assert len(ciphertext) > len(original_pat)
    
    decrypted = decrypt_secret(ciphertext)
    assert decrypted == original_pat


def test_jwt_token_generation_and_validation():
    """Verify that JWT session tokens are correctly created, signed, and decoded."""
    payload_data = {"sub": "42", "username": "octocat", "github_id": "123456"}
    token = create_access_token(payload_data, expires_delta=datetime.timedelta(minutes=30))
    
    assert isinstance(token, str)
    assert len(token.split(".")) == 3  # Header.Payload.Signature
    
    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "42"
    assert decoded["username"] == "octocat"
    assert decoded["github_id"] == "123456"
    assert "exp" in decoded


def test_jwt_invalid_token_handling():
    """Verify that malformed or tampered JWT tokens return None."""
    assert decode_access_token("invalid.token.structure") is None
    assert decode_access_token("") is None


@pytest.mark.asyncio
async def test_auth_me_endpoint_authenticated():
    """Verify /api/auth/me returns user profile when valid session cookie is provided."""
    mock_db = AsyncMock()
    mock_user = User(
        id=1,
        github_id="1001",
        username="anmolsharma152",
        display_name="Anmol Sharma",
        email="anmol@example.com",
        avatar_url="https://github.com/anmolsharma152.png",
        github_token=encrypt_secret("ghp_test123"),
        tier="free"
    )
    mock_db.get = AsyncMock(return_value=mock_user)

    app.dependency_overrides[get_db] = lambda: mock_db
    token = create_access_token({"sub": "1", "username": "anmolsharma152"})

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies={"nimbus_session": token}) as ac:
        response = await ac.get("/api/auth/me")
        app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is True
        assert data["user"]["username"] == "anmolsharma152"
        assert data["user"]["has_github_token"] is True


@pytest.mark.asyncio
async def test_auth_me_endpoint_unauthenticated():
    """Verify /api/auth/me returns 401 when no session token is provided."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/auth/me")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_logout_clears_cookie():
    """Verify /api/auth/logout deletes the nimbus_session cookie."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/auth/logout")
        assert response.status_code == 200
        assert "nimbus_session" in response.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_user_scoped_task_isolation():
    """Verify that User A cannot view or access User B's task."""
    mock_db = AsyncMock()
    
    # Task owned by User #99
    other_user_task = Task(
        id=5,
        user_id=99,
        prompt="Secret task by user 99",
        status=TaskStatus.COMPLETED
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = other_user_task
    mock_db.execute.return_value = mock_result

    # Current authenticated user is User #1
    current_user = User(id=1, github_id="1", username="user1")
    mock_db.get = AsyncMock(return_value=current_user)

    app.dependency_overrides[get_db] = lambda: mock_db
    token = create_access_token({"sub": "1", "username": "user1"})

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies={"nimbus_session": token}) as ac:
        # Requesting task 5 (owned by user 99)
        response = await ac.get("/api/tasks/5")
        assert response.status_code == 404

        # Requesting events of task 5
        response_events = await ac.get("/api/tasks/5/events")
        assert response_events.status_code == 404

        # Requesting screenshots of task 5
        response_screens = await ac.get("/api/tasks/5/screenshots")
        assert response_screens.status_code == 404

        # Requesting cancel on task 5
        response_cancel = await ac.post("/api/tasks/5/cancel")
        assert response_cancel.status_code == 404

        # Requesting delete on task 5
        response_delete = await ac.delete("/api/tasks/5")
        assert response_delete.status_code == 404

    # Unauthenticated user without cookie requesting task 5
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac_anon:
        response_anon = await ac_anon.get("/api/tasks/5")
        assert response_anon.status_code == 404

        response_anon_events = await ac_anon.get("/api/tasks/5/events")
        assert response_anon_events.status_code == 404
    
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_repos_proxy_endpoint():
    """Verify /api/repos proxies repositories for the user."""
    mock_user = User(
        id=1,
        github_id="1",
        username="testdev",
        github_token=encrypt_secret("ghp_fakeToken")
    )
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_user)
    app.dependency_overrides[get_db] = lambda: mock_db
    token = create_access_token({"sub": "1", "username": "testdev"})

    fake_github_repos = [
        {
            "id": 101,
            "name": "super-agent",
            "full_name": "testdev/super-agent",
            "html_url": "https://github.com/testdev/super-agent",
            "stargazers_count": 12,
            "language": "Python",
            "description": "An autonomous agent",
            "private": False
        }
    ]

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = fake_github_repos
        mock_get.return_value = mock_resp

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies={"nimbus_session": token}) as ac:
            response = await ac.get("/api/repos")
            app.dependency_overrides.clear()

            assert response.status_code == 200
            repos = response.json()
            assert len(repos) == 1
            assert repos[0]["name"] == "super-agent"
            assert repos[0]["stargazers_count"] == 12
