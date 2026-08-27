"""Encrypted Credential Vault & User Onboarding API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel, Field
from typing import List, Optional
import datetime

from .db import get_db
from .models import User, UserCredential
from .auth import get_current_user
from .security import encrypt_secret, decrypt_secret

router = APIRouter(prefix="/api/settings/credentials", tags=["credentials"])

ALLOWED_PROVIDERS = {"gemini", "groq", "openrouter", "github_pat"}


class CredentialItem(BaseModel):
    provider: str
    configured: bool
    updated_at: Optional[str] = None


class CredentialSaveRequest(BaseModel):
    value: str = Field(..., min_length=1, description="Plaintext API key or Personal Access Token to encrypt.")


class OnboardingCompleteResponse(BaseModel):
    ok: bool
    onboarding_completed: bool


@router.get("", response_model=List[CredentialItem])
async def list_user_credentials(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns the list of configured AI provider keys and personal access tokens
    stored in the encrypted vault for the authenticated user.
    Plaintext secrets are never returned.
    """
    result = await db.execute(select(UserCredential).where(UserCredential.user_id == user.id))
    creds = result.scalars().all()
    configured_map = {c.provider: c for c in creds}

    items = []
    for provider in sorted(list(ALLOWED_PROVIDERS)):
        item = configured_map.get(provider)
        items.append(
            CredentialItem(
                provider=provider,
                configured=item is not None,
                updated_at=item.updated_at.isoformat() if item and item.updated_at else None
            )
        )
    return items


@router.put("/{provider}")
async def save_user_credential(
    provider: str,
    req: CredentialSaveRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Encrypts and persists an API key or GitHub PAT in the user's credential vault.
    """
    clean_provider = provider.strip().lower()
    if clean_provider not in ALLOWED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported provider '{provider}'. Must be one of: {', '.join(sorted(ALLOWED_PROVIDERS))}"
        )

    clean_value = req.value.strip()
    if not clean_value:
        raise HTTPException(status_code=400, detail="Credential value cannot be empty.")

    encrypted_val = encrypt_secret(clean_value)
    if not encrypted_val:
        raise HTTPException(status_code=500, detail="Encryption failure.")

    result = await db.execute(
        select(UserCredential).where(
            UserCredential.user_id == user.id,
            UserCredential.provider == clean_provider
        )
    )
    cred = result.scalar_one_or_none()

    if not cred:
        cred = UserCredential(
            user_id=user.id,
            provider=clean_provider,
            encrypted_value=encrypted_val
        )
        db.add(cred)
    else:
        cred.encrypted_value = encrypted_val
        cred.updated_at = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    await db.commit()
    await db.refresh(cred)

    return {
        "ok": True,
        "provider": clean_provider,
        "message": f"Successfully encrypted and saved {clean_provider} credential."
    }


@router.delete("/{provider}")
async def delete_user_credential(
    provider: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Removes a provider credential from the user's encrypted vault.
    """
    clean_provider = provider.strip().lower()
    result = await db.execute(
        select(UserCredential).where(
            UserCredential.user_id == user.id,
            UserCredential.provider == clean_provider
        )
    )
    cred = result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail=f"No credential configured for '{provider}'.")

    await db.delete(cred)
    await db.commit()

    return {
        "ok": True,
        "provider": clean_provider,
        "message": f"Successfully deleted {clean_provider} credential."
    }


# Router for user onboarding status
user_router = APIRouter(prefix="/api/users", tags=["users"])


@user_router.post("/onboarding-complete", response_model=OnboardingCompleteResponse)
async def mark_onboarding_complete(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Marks the user's interactive onboarding wizard as completed.
    """
    user.onboarding_completed = True
    await db.commit()
    await db.refresh(user)
    return OnboardingCompleteResponse(ok=True, onboarding_completed=True)
