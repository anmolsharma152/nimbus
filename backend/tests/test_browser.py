import pytest
import os
import tempfile
import base64
import json
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from httpx import ASGITransport

from app.main import app
from app.models import User, Task, TaskEvent, EventType
from app.workspace import UnifiedWorkspace, SubprocessWorkspace
from app.db import get_db


@pytest.mark.asyncio
async def test_subprocess_workspace_get_file_base64():
    """Verify that SubprocessWorkspace reads and encodes binary files to base64."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test_screenshot.png")
        fake_png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfakeimagedata"
        with open(test_file, "wb") as f:
            f.write(fake_png_data)

        workspace = SubprocessWorkspace(task_id=999)
        workspace.workdir = tmpdir

        b64_out = workspace.get_file_base64("test_screenshot.png")
        assert b64_out is not None
        assert base64.b64decode(b64_out) == fake_png_data


@pytest.mark.asyncio
async def test_unified_workspace_aget_file_base64():
    """Verify that UnifiedWorkspace properly delegates aget_file_base64."""
    workspace = UnifiedWorkspace(task_id=999)
    workspace.impl = MagicMock()
    workspace.impl.get_file_base64.return_value = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"

    res = await workspace.aget_file_base64("preview.png")
    assert res == "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
    workspace.impl.get_file_base64.assert_called_with("preview.png")


@pytest.mark.asyncio
async def test_get_screenshots_endpoint():
    """Verify GET /api/tasks/{task_id}/screenshots returns visual artifact list."""
    from app.security import create_access_token
    mock_user = User(id=1, username="testdev")
    mock_task = Task(id=10, user_id=1, prompt="Test screenshot")
    
    mock_event = TaskEvent(
        id=55,
        task_id=10,
        event_type=EventType.RESULT,
        payload=json.dumps({
            "screenshot": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            "filename": "landing.png",
            "caption": "Landing page component test"
        })
    )

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_user)
    
    mock_task_res = MagicMock()
    mock_task_res.scalar_one_or_none.return_value = mock_task
    
    mock_events_res = MagicMock()
    mock_events_res.scalars.return_value.all.return_value = [mock_event]

    mock_db.execute = AsyncMock(side_effect=[mock_task_res, mock_events_res])
    app.dependency_overrides[get_db] = lambda: mock_db

    token = create_access_token({"sub": "1", "username": "testdev"})

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", cookies={"nimbus_session": token}) as ac:
        response = await ac.get("/api/tasks/10/screenshots")
        app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["filename"] == "landing.png"
        assert data[0]["caption"] == "Landing page component test"
        assert "data:image/png;base64" in data[0]["data"]
