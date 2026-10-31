"""Per-user model preferences are validated, stored on the account and used by the worker."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport

from app.auth import get_current_user
from app.db import get_db
from app.llm import LLMChatSession
from app.main import app
from app.model_prefs import ALLOWED_MODELS, parse_model_prefs
from app.models import Task, TaskStatus, User


@pytest.fixture
def signed_in():
    user = User(id=1, github_id="1", username="dev", model_prefs=None)
    db = AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    yield user, db
    app.dependency_overrides.clear()


async def _call(method, path, json_body=None):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        return await ac.request(method, path, json=json_body)


def test_parse_drops_unknown_providers_models_and_garbage():
    raw = json.dumps({"gemini": "gemini-3.7-flash", "groq": "not-a-model", "other": "x"})
    assert parse_model_prefs(raw) == {"gemini": "gemini-3.7-flash"}
    assert parse_model_prefs(None) == {}
    assert parse_model_prefs("{not json") == {}
    assert parse_model_prefs('["list"]') == {}


@pytest.mark.asyncio
async def test_get_returns_saved_choices_and_options(signed_in):
    user, _ = signed_in
    user.model_prefs = json.dumps({"groq": "llama-3.3-70b-versatile"})
    resp = await _call("GET", "/api/settings/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["groq"] == "llama-3.3-70b-versatile" and data["gemini"] is None
    assert data["options"]["openrouter"] == list(ALLOWED_MODELS["openrouter"])


@pytest.mark.asyncio
async def test_put_saves_only_set_values(signed_in):
    user, db = signed_in
    resp = await _call("PUT", "/api/settings/models", {"gemini": "gemini-3.5-flash", "groq": None})
    assert resp.status_code == 200
    assert json.loads(user.model_prefs) == {"gemini": "gemini-3.5-flash"}
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_put_clearing_everything_stores_null(signed_in):
    user, _ = signed_in
    user.model_prefs = json.dumps({"gemini": "gemini-3.5-flash"})
    resp = await _call("PUT", "/api/settings/models", {})
    assert resp.status_code == 200 and user.model_prefs is None


@pytest.mark.asyncio
async def test_put_rejects_models_outside_the_allowlist(signed_in):
    user, db = signed_in
    resp = await _call("PUT", "/api/settings/models", {"openrouter": "some/paid-model"})
    assert resp.status_code == 422
    assert user.model_prefs is None and not db.commit.called


@pytest.mark.asyncio
async def test_endpoints_require_sign_in():
    app.dependency_overrides.clear()
    assert (await _call("GET", "/api/settings/models")).status_code == 401
    assert (await _call("PUT", "/api/settings/models", {})).status_code == 401


def test_session_puts_chosen_gemini_model_first_and_uses_chosen_fallback_models():
    session = LLMChatSession(
        system_instruction="s", gemini_model="gemini-3.5-flash", groq_model="qwen/qwen3.6-27b",
        openrouter_model="google/gemma-4-31b-it:free",
    )
    assert session._gemini_models[0] == "gemini-3.5-flash"
    assert session._gemini_models.count("gemini-3.5-flash") == 1
    assert session.groq_model == "qwen/qwen3.6-27b"
    assert session.openrouter_model == "google/gemma-4-31b-it:free"


def test_session_defaults_without_preferences():
    session = LLMChatSession(system_instruction="s")
    assert session._gemini_models[0] == "gemini-3.6-flash"
    assert session.groq_model and session.openrouter_model


@pytest.mark.asyncio
async def test_worker_passes_user_model_prefs_to_llm_session():
    from app.worker import run_agent_loop

    task = Task(id=31, user_id=1, prompt="p", status=TaskStatus.PENDING)
    user = User(id=1, github_id="1", username="dev", model_prefs=json.dumps({"groq": "llama-3.3-70b-versatile"}))
    db = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock(side_effect=[task, user])
    empty = MagicMock()
    empty.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=empty)
    ws = MagicMock()
    ws.base_sha = None
    ws.asetup = AsyncMock(return_value=(0, ""))
    ws.aexecute_command = AsyncMock(return_value=(0, ""))
    ws.acleanup = AsyncMock()

    with patch("app.worker.settings.GEMINI_API_KEY", "k"), \
         patch("app.worker.async_session") as session_ctx, \
         patch("app.worker.UnifiedWorkspace", return_value=ws), \
         patch("app.worker.LLMChatSession") as llm_cls, \
         patch("app.worker.run_agent_commands", new_callable=AsyncMock, return_value="cancelled"), \
         patch("app.worker.log_event", new_callable=AsyncMock):
        session_ctx.return_value.__aenter__.return_value = db
        await run_agent_loop(ctx={}, task_id=31, prompt="p")

    kwargs = llm_cls.call_args.kwargs
    assert kwargs["groq_model"] == "llama-3.3-70b-versatile"
    assert kwargs["gemini_model"] is None and kwargs["openrouter_model"] is None
