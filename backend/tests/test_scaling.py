import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from fastapi import HTTPException
from httpx import ASGITransport

from app.main import app
from app.models import User, Task, TaskEvent, TaskStatus, EventType
from app.security import create_access_token
from app.ratelimit import check_task_submission_limits
from app.events import RedisEventBus


@pytest.mark.asyncio
async def test_rate_limit_allows_within_quota():
    """Verify that a user under quota is allowed to submit a task."""
    mock_user = User(id=1, username="testdev", tier="free")
    mock_db = AsyncMock()
    
    # Mock 1 active task (below free tier limit of 3)
    mock_res_active = MagicMock()
    mock_res_active.scalar.return_value = 1
    
    # Mock 5 tasks in last hour (below limit of 20)
    mock_res_hourly = MagicMock()
    mock_res_hourly.scalar.return_value = 5

    mock_db.execute = AsyncMock(side_effect=[mock_res_active, mock_res_hourly])

    # Should not raise any exception
    await check_task_submission_limits(mock_user, mock_db)


@pytest.mark.asyncio
async def test_rate_limit_rejects_exceeded_concurrency():
    """Verify that exceeding active concurrent tasks raises 429."""
    mock_user = User(id=1, username="testdev", tier="free")
    mock_db = AsyncMock()
    
    # Mock 3 active tasks (hits free tier max of 3)
    mock_res_active = MagicMock()
    mock_res_active.scalar.return_value = 3
    mock_db.execute = AsyncMock(return_value=mock_res_active)

    with pytest.raises(HTTPException) as exc_info:
        await check_task_submission_limits(mock_user, mock_db)

    assert exc_info.value.status_code == 429
    assert "Concurrency quota exceeded" in exc_info.value.detail


@pytest.mark.asyncio
async def test_rate_limit_rejects_anonymous_capacity():
    """Verify that exceeding anonymous concurrent tasks raises 429."""
    mock_db = AsyncMock()
    
    # Mock 2 anonymous active tasks
    mock_res_active = MagicMock()
    mock_res_active.scalar.return_value = 2
    mock_db.execute = AsyncMock(return_value=mock_res_active)

    with pytest.raises(HTTPException) as exc_info:
        await check_task_submission_limits(None, mock_db)

    assert exc_info.value.status_code == 429
    assert "Anonymous task capacity reached" in exc_info.value.detail


@pytest.mark.asyncio
async def test_redis_event_bus_publish():
    """Verify RedisEventBus formats and publishes events."""
    bus = RedisEventBus()
    mock_redis = AsyncMock()
    bus._redis = mock_redis

    await bus.publish_event(
        task_id=42,
        event_type="log",
        payload_dict={"message": "Sandbox initialized"},
        timestamp="2026-08-27T12:00:00Z"
    )

    assert mock_redis.publish.called
    assert mock_redis.xadd.called
    
    channel = mock_redis.publish.call_args[0][0]
    message_str = mock_redis.publish.call_args[0][1]
    
    assert channel == "nimbus:events:task:42"
    assert "Sandbox initialized" in message_str
    assert '"type": "log"' in message_str
