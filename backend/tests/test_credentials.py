import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from httpx import ASGITransport

from app.main import app
from app.models import User, UserCredential
from app.security import create_access_token, encrypt_secret, decrypt_secret
from app.db import get_db


@pytest.mark.asyncio
async def test_list_credentials_authenticated():
    """Verify listing credentials returns provider status without leaking secrets."""
    mock_user = User(id=1, github_id="1", username="testdev")
    mock_cred = UserCredential(
        id=10,
        user_id=1,
        provider="gemini",
        encrypted_value=encrypt_secret("AIzaSyFakeGeminiKey123")
    )
    
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_user)
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_cred]
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: mock_db
    token = create_access_token({"sub": "1", "username": "testdev"})

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies={"nimbus_session": token}) as ac:
        response = await ac.get("/api/settings/credentials")
        app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Check providers list
        providers = {item["provider"]: item["configured"] for item in data}
        assert providers["gemini"] is True
        assert providers["groq"] is False
        assert providers["openrouter"] is False
        
        # Ensure no plaintext secret leaked in response
        raw_text = response.text
        assert "AIzaSyFakeGeminiKey123" not in raw_text


@pytest.mark.asyncio
async def test_save_credential_encrypts_and_persists():
    """Verify PUT /api/settings/credentials/{provider} encrypts and saves."""
    mock_user = User(id=1, github_id="1", username="testdev")
    
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_user)
    
    # Mock no existing credential for this provider
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    app.dependency_overrides[get_db] = lambda: mock_db
    token = create_access_token({"sub": "1", "username": "testdev"})

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies={"nimbus_session": token}) as ac:
        response = await ac.put(
            "/api/settings/credentials/groq",
            json={"value": "gsk_superSecretGroqKey123"}
        )
        app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["provider"] == "groq"
        assert mock_db.add.called

        # Verify that the value added was encrypted
        added_cred = mock_db.add.call_args[0][0]
        assert added_cred.encrypted_value != "gsk_superSecretGroqKey123"
        assert decrypt_secret(added_cred.encrypted_value) == "gsk_superSecretGroqKey123"


@pytest.mark.asyncio
async def test_delete_credential():
    """Verify DELETE /api/settings/credentials/{provider} removes the record."""
    mock_user = User(id=1, github_id="1", username="testdev")
    mock_cred = UserCredential(id=10, user_id=1, provider="openrouter", encrypted_value="enc_val")
    
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_user)
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_cred
    mock_db.execute.return_value = mock_result
    mock_db.delete = AsyncMock()
    mock_db.commit = AsyncMock()

    app.dependency_overrides[get_db] = lambda: mock_db
    token = create_access_token({"sub": "1", "username": "testdev"})

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies={"nimbus_session": token}) as ac:
        response = await ac.delete("/api/settings/credentials/openrouter")
        app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert mock_db.delete.called


@pytest.mark.asyncio
async def test_save_unsupported_provider_rejected():
    """Verify that attempting to save an invalid provider is rejected with 400."""
    mock_user = User(id=1, github_id="1", username="testdev")
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_user)
    app.dependency_overrides[get_db] = lambda: mock_db
    token = create_access_token({"sub": "1", "username": "testdev"})

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies={"nimbus_session": token}) as ac:
        response = await ac.put(
            "/api/settings/credentials/unsupported_ai_vendor",
            json={"value": "some_key"}
        )
        app.dependency_overrides.clear()

        assert response.status_code == 400
        assert "Unsupported provider" in response.json()["detail"]


@pytest.mark.asyncio
async def test_onboarding_complete_endpoint():
    """Verify POST /api/users/onboarding-complete updates user state."""
    mock_user = User(id=1, github_id="1", username="testdev", onboarding_completed=False)
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_user)
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    app.dependency_overrides[get_db] = lambda: mock_db
    token = create_access_token({"sub": "1", "username": "testdev"})

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies={"nimbus_session": token}) as ac:
        response = await ac.post("/api/users/onboarding-complete")
        app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert response.json()["onboarding_completed"] is True
        assert mock_user.onboarding_completed is True
