import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json

from app.worker import log_event, run_agent_loop
from app.models import EventType, TaskStatus, Task


@pytest.mark.asyncio
async def test_log_event_saves_and_broadcasts():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        
        await log_event(
            db=mock_db,
            task_id=1,
            event_type=EventType.COMMAND,
            payload_dict={"command": "git status"}
        )

        assert mock_db.add.called
        assert mock_db.commit.called


@pytest.mark.asyncio
async def test_run_agent_loop_missing_api_key():
    fake_task = Task(id=2, prompt="Test prompt", status=TaskStatus.PENDING)
    mock_db = AsyncMock()
    mock_db.get.return_value = fake_task
    mock_db.commit = AsyncMock()

    with patch("app.worker.settings.GEMINI_API_KEY", None), \
         patch("app.worker.settings.GROQ_API_KEY", None), \
         patch("app.worker.settings.OPENROUTER_API_KEY", None), \
         patch("app.worker.async_session") as mock_session_ctx, \
         patch("app.worker.log_event", new_callable=AsyncMock) as mock_log:
        
        mock_session_ctx.return_value.__aenter__.return_value = mock_db

        await run_agent_loop(ctx={}, task_id=2, prompt="Test prompt")
        assert fake_task.status == TaskStatus.FAILED
        assert mock_log.called


def test_command_json_extraction():
    # Helper to test LLM output parsing logic from worker
    def extract_command(text: str):
        if "```json" in text and "\"command\":" in text:
            json_str = text.split("```json")[1].split("```")[0].strip()
            return json.loads(json_str).get("command")
        return None

    sample_llm_output = (
        "I will now list the files in the repository:\n"
        "```json\n"
        "{\n"
        "  \"command\": \"pytest tests/\"\n"
        "}\n"
        "```\n"
    )
    assert extract_command(sample_llm_output) == "pytest tests/"

    invalid_output = "I have completed all the requested tasks!"
    assert extract_command(invalid_output) is None


def test_normalize_redis_url():
    from app.worker import normalize_redis_url

    assert normalize_redis_url("") == "redis://localhost:6379/0"
    assert normalize_redis_url("   ") == "redis://localhost:6379/0"
    assert normalize_redis_url(None) == "redis://localhost:6379/0"
    assert normalize_redis_url('"rediss://default:pass@us1.upstash.io:6379"') == "rediss://default:pass@us1.upstash.io:6379"
    assert normalize_redis_url("'rediss://default:pass@us1.upstash.io:6379'") == "rediss://default:pass@us1.upstash.io:6379"
    assert normalize_redis_url("redis-cli --tls -u rediss://default:pass@us1.upstash.io:6379") == "rediss://default:pass@us1.upstash.io:6379"
    assert normalize_redis_url("https://invalid.com") == "redis://localhost:6379/0"
