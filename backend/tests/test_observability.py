import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport

from app.db import get_db
from app.logging_config import (
    ContextFilter,
    JsonFormatter,
    TextFormatter,
    new_request_id,
    request_id_var,
    task_id_var,
)
from app.main import app
from app.models import Task, TaskStatus


def _record(msg="hello", **extra):
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, msg, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    ContextFilter().filter(record)
    return record


# --- Formatters and context ---

def test_json_logs_carry_request_and_task_context_and_extra_fields():
    rid_token, tid_token = request_id_var.set("req-123"), task_id_var.set(42)
    try:
        line = JsonFormatter().format(_record(event="task_finished", duration_s=1.5))
    finally:
        request_id_var.reset(rid_token)
        task_id_var.reset(tid_token)

    entry = json.loads(line)
    assert entry["message"] == "hello"
    assert entry["level"] == "INFO"
    assert entry["request_id"] == "req-123"
    assert entry["task_id"] == 42
    assert entry["event"] == "task_finished"
    assert entry["duration_s"] == 1.5


def test_explicit_request_id_overrides_context():
    entry = json.loads(JsonFormatter().format(_record(request_id="explicit")))
    assert entry["request_id"] == "explicit"


def test_json_logs_include_exceptions():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = logging.LogRecord("app.test", logging.ERROR, __file__, 1, "failed", None, sys.exc_info())
    ContextFilter().filter(record)
    entry = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in entry["exc_info"]


def test_text_format_shows_context_inline():
    token = task_id_var.set(7)
    try:
        line = TextFormatter().format(_record(event="x"))
    finally:
        task_id_var.reset(token)
    assert "task_id=7" in line and "event=x" in line


def test_request_ids_are_sanitized():
    assert new_request_id("abc-123_DEF.4") == "abc-123_DEF.4"
    for bad in ("evil\ninjected line", "x" * 65, "", None, "a b"):
        generated = new_request_id(bad)
        assert generated != bad and len(generated) == 16


# --- HTTP request context ---

@pytest.mark.asyncio
async def test_responses_carry_request_id():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        generated = await ac.get("/healthz")
        echoed = await ac.get("/healthz", headers={"X-Request-ID": "client-abc"})
        sanitized = await ac.get("/healthz", headers={"X-Request-ID": "bad id\r\nX-Evil: 1"})

    assert len(generated.headers["X-Request-ID"]) == 16
    assert echoed.headers["X-Request-ID"] == "client-abc"
    assert sanitized.headers["X-Request-ID"] != "bad id\r\nX-Evil: 1"


@pytest.mark.asyncio
async def test_unhandled_errors_hide_traceback_and_return_request_id(caplog):
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=RuntimeError("secret internal detail"))
    app.dependency_overrides[get_db] = lambda: db
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            with caplog.at_level(logging.ERROR, logger="app.main"):
                response = await ac.get("/api/tasks", headers={"X-Request-ID": "trace-me"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    body = response.json()
    assert body == {"detail": "Internal server error", "request_id": "trace-me"}
    assert "secret internal detail" not in response.text
    assert response.headers["X-Request-ID"] == "trace-me"

    errors = [r for r in caplog.records if getattr(r, "event", None) == "unhandled_error"]
    assert errors and errors[0].request_id == "trace-me"
    assert "secret internal detail" in str(errors[0].exc_info[1])


# --- Worker task summary ---

class _Collect(logging.Handler):
    def __init__(self):
        super().__init__()
        self.addFilter(ContextFilter())
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.mark.asyncio
async def test_worker_logs_task_context_and_one_summary_per_task():
    from app.worker import run_agent_loop

    task = Task(id=5, prompt="secret prompt text", status=TaskStatus.PENDING)
    db = AsyncMock()
    db.get = AsyncMock(return_value=task)
    db.add = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock())  # SQLAlchemy results are sync objects
    ws = MagicMock()
    ws.asetup = AsyncMock(return_value=(128, "Failed to set up workspace"))
    ws.acleanup = AsyncMock()

    handler = _Collect()
    worker_logger = logging.getLogger("app.worker")
    worker_logger.addHandler(handler)
    worker_logger.setLevel(logging.INFO)
    try:
        with patch("app.worker.settings.GEMINI_API_KEY", "k"), \
             patch("app.worker.async_session") as mock_session_ctx, \
             patch("app.worker.UnifiedWorkspace", return_value=ws), \
             patch("app.worker.log_event", new_callable=AsyncMock):
            mock_session_ctx.return_value.__aenter__.return_value = db
            await run_agent_loop(ctx={}, task_id=5, prompt="secret prompt text")
    finally:
        worker_logger.removeHandler(handler)

    assert handler.records and all(r.task_id == 5 for r in handler.records)
    assert task_id_var.get() is None  # context restored after the task
    summaries = [r for r in handler.records if getattr(r, "event", None) == "task_finished"]
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.task_status == "failed"
    assert summary.reason == "RuntimeError"
    assert summary.duration_s >= 0
    assert all("secret prompt text" not in r.getMessage() and "secret prompt text" not in str(vars(r)) for r in handler.records)


# --- LLM usage counters ---

@pytest.mark.asyncio
async def test_llm_session_counts_calls_and_failures_per_tier():
    from app.llm import LLMChatSession

    with patch("app.llm.settings.GEMINI_API_KEY", "k"), \
         patch("app.llm.settings.GROQ_API_KEY", "g"), \
         patch("app.llm.settings.OPENROUTER_API_KEY", None), \
         patch("app.llm.genai.Client"):
        session = LLMChatSession(system_instruction="s")
        session._call_gemini = AsyncMock(side_effect=RuntimeError("503 unavailable"))
        session._call_groq = AsyncMock(return_value="ok")
        assert await session.send_message("hi") == "ok"

        session._call_groq = AsyncMock(side_effect=RuntimeError("429"))
        with pytest.raises(RuntimeError):
            await session.send_message("again")

    assert session.tier_calls == {"groq": 1}
    # OpenRouter has no key: skipped, not counted as a provider failure
    assert session.tier_failures == {"gemini": 2, "groq": 1}
    assert session.llm_seconds >= 0
