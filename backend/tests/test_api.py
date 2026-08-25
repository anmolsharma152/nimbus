import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from httpx import ASGITransport

from app.main import app, manager
from app.models import Task, TaskStatus, EventType


@pytest.mark.asyncio
async def test_create_task_endpoint():
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    # Mock enqueue_task so we don't need real Redis
    with patch("app.main.enqueue_task", new_callable=AsyncMock) as mock_enqueue:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            payload = {
                "prompt": "Fix bug in authentication",
                "repo_url": "https://github.com/example/repo",
                "git_branch": "nimbus/task-1"
            }
            # We override get_db dependency
            from app.db import get_db
            app.dependency_overrides[get_db] = lambda: mock_db

            response = await ac.post("/api/tasks", json=payload)
            app.dependency_overrides.clear()

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pending"
            assert data["repo_url"] == "https://github.com/example/repo"
            assert data["git_branch"] == "nimbus/task-1"
            assert mock_enqueue.called


@pytest.mark.asyncio
async def test_get_task_not_found():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    from app.db import get_db
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/tasks/99999")
        app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["error"] == "Task not found"


@pytest.mark.asyncio
async def test_get_task_success():
    fake_task = Task(
        id=101,
        prompt="Add unit tests",
        repo_url="https://github.com/org/repo",
        git_branch="nimbus/task-101",
        pr_url="https://github.com/org/repo/pull/1",
        patch_diff="diff --git a/test.py b/test.py",
        status=TaskStatus.COMPLETED
    )
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_task
    mock_db.execute.return_value = mock_result

    from app.db import get_db
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/tasks/101")
        app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 101
        assert data["status"] == "completed"
        assert data["prompt"] == "Add unit tests"
        assert data["repo_url"] == "https://github.com/org/repo"
        assert data["pr_url"] == "https://github.com/org/repo/pull/1"
        assert "diff --git" in data["patch_diff"]


@pytest.mark.asyncio
async def test_internal_event_broadcast():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {"type": "log", "message": "Test event"}
        response = await ac.post("/api/internal/tasks/101/events", json=payload)
        assert response.status_code == 200
        assert response.json() == {"ok": True}


@pytest.mark.asyncio
async def test_cancel_task_endpoint():
    fake_task = Task(id=202, prompt="Long running task", status=TaskStatus.RUNNING)
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_task
    mock_db.execute.return_value = mock_result
    mock_db.commit = AsyncMock()

    from app.db import get_db
    app.dependency_overrides[get_db] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/api/tasks/202/cancel")
        app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 202
        assert data["status"] == "cancelled"
        assert fake_task.status == TaskStatus.CANCELLED
        assert mock_db.commit.called
