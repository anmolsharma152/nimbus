"""Per-user LLM model preferences: which model each provider tier uses for this user's tasks."""

import json
from typing import Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .db import get_db
from .models import User

# Only these may be chosen; the Settings modal offers exactly these options
ALLOWED_MODELS: Dict[str, tuple] = {
    "gemini": ("gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash"),
    "groq": ("openai/gpt-oss-120b", "llama-3.3-70b-versatile", "qwen/qwen3.6-27b"),
    "openrouter": ("cohere/north-mini-code:free", "google/gemma-4-31b-it:free"),
}

router = APIRouter(prefix="/api/settings/models", tags=["settings"])


def parse_model_prefs(raw: Optional[str]) -> Dict[str, str]:
    """Stored JSON -> {provider: model}, silently dropping anything no longer allowed."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        provider: model for provider, model in data.items()
        if provider in ALLOWED_MODELS and model in ALLOWED_MODELS[provider]
    }


class ModelPrefs(BaseModel):
    gemini: Optional[str] = None
    groq: Optional[str] = None
    openrouter: Optional[str] = None

    @field_validator("gemini", "groq", "openrouter")
    @classmethod
    def _allowed(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None and v not in ALLOWED_MODELS[info.field_name]:
            raise ValueError(f"Unsupported {info.field_name} model: {v}")
        return v


class ModelPrefsResponse(ModelPrefs):
    options: Dict[str, list]


def _response(prefs: Dict[str, str]) -> ModelPrefsResponse:
    return ModelPrefsResponse(**prefs, options={k: list(v) for k, v in ALLOWED_MODELS.items()})


@router.get("", response_model=ModelPrefsResponse)
async def get_model_prefs(user: User = Depends(get_current_user)):
    """The user's saved choices (unset = server default) and the allowed options."""
    return _response(parse_model_prefs(user.model_prefs))


@router.put("", response_model=ModelPrefsResponse)
async def save_model_prefs(
    req: ModelPrefs,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    prefs = {k: v for k, v in req.model_dump().items() if v is not None}
    user.model_prefs = json.dumps(prefs) if prefs else None
    await db.commit()
    return _response(prefs)
