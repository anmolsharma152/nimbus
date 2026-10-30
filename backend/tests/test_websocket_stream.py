import asyncio
import json
import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app, manager, ConnectionManager, relay_redis_events
from app.models import Task, TaskEvent, TaskStatus, EventType


def _session_factory(task, events=()):
    """Mimics `async with async_session() as db`, recording every session opened."""
    sessions = []

    def factory():
        db = AsyncMock()
        db.get = AsyncMock(return_value=task)
        result = MagicMock()
        result.scalars.return_value.all.return_value = list(events)
        db.execute = AsyncMock(return_value=result)
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=db)
        cm.__aexit__ = AsyncMock(return_value=False)
        sessions.append((cm, db))
        return cm

    return factory, sessions


def _event(event_id, message):
    return TaskEvent(
        id=event_id, task_id=1, event_type=EventType.LOG,
        payload=json.dumps({"message": message}), created_at=datetime.datetime(2026, 10, 31, 12, 0, event_id)
    )


@pytest.fixture(autouse=True)
def clear_manager():
    manager.active_connections.clear()
    yield
    manager.active_connections.clear()


def test_unauthorized_stream_is_accepted_then_closed_with_1008():
    """Rejecting before accept surfaces as 1006 in browsers, so clients can't tell auth failures apart."""
    factory, _ = _session_factory(Task(id=1, user_id=99, prompt="p", status=TaskStatus.RUNNING))
    with patch("app.main.async_session", factory):
        with TestClient(app).websocket_connect("/ws/tasks/1") as ws:  # handshake must succeed
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_text()
    assert exc.value.code == 1008


def test_missing_task_closes_with_1008():
    factory, _ = _session_factory(None)
    with patch("app.main.async_session", factory):
        with TestClient(app).websocket_connect("/ws/tasks/404") as ws:
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_text()
    assert exc.value.code == 1008


def test_history_replay_includes_ids_and_releases_db_sessions():
    task = Task(id=1, user_id=None, prompt="p", status=TaskStatus.RUNNING)
    factory, sessions = _session_factory(task, [_event(5, "a"), _event(6, "b")])
    with patch("app.main.async_session", factory):
        with TestClient(app).websocket_connect("/ws/tasks/1") as ws:
            first = json.loads(ws.receive_text())
            second = json.loads(ws.receive_text())
            # Streaming continues without holding a pooled DB connection
            assert sessions and all(cm.__aexit__.await_count == 1 for cm, _ in sessions)

    assert (first["id"], second["id"]) == (5, 6)
    assert json.loads(first["payload"]) == {"message": "a"}


def test_resume_cursor_only_replays_newer_events():
    task = Task(id=1, user_id=None, prompt="p", status=TaskStatus.RUNNING)
    factory, sessions = _session_factory(task, [_event(9, "new")])
    with patch("app.main.async_session", factory):
        with TestClient(app).websocket_connect("/ws/tasks/1?after=8") as ws:
            assert json.loads(ws.receive_text())["id"] == 9

    history_query = str(sessions[-1][1].execute.call_args.args[0])
    assert "task_events.id >" in history_query


def test_connection_is_unregistered_after_client_disconnects():
    task = Task(id=1, user_id=None, prompt="p", status=TaskStatus.RUNNING)
    factory, _ = _session_factory(task, [_event(1, "a")])
    with patch("app.main.async_session", factory):
        with TestClient(app).websocket_connect("/ws/tasks/1") as ws:
            ws.receive_text()
            assert 1 in manager.active_connections
    assert 1 not in manager.active_connections


# --- ConnectionManager fan-out ---

def _socket(send=None):
    ws = MagicMock()
    ws.send_text = send or AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_broadcast_prunes_dead_sockets_and_keeps_healthy_ones():
    mgr = ConnectionManager()
    healthy = _socket()
    dead = _socket(AsyncMock(side_effect=RuntimeError("closed")))
    mgr.register(healthy, 1)
    mgr.register(dead, 1)

    await mgr.broadcast_event(1, {"id": 1, "type": "log", "payload": "{}"})

    assert mgr.active_connections[1] == [healthy]
    healthy.send_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_broadcast_drops_duplicate_event_ids():
    """The same event arrives via Redis pub/sub and the worker's HTTP fallback."""
    mgr = ConnectionManager()
    ws = _socket()
    mgr.register(ws, 1)

    await mgr.broadcast_event(1, {"id": 7, "type": "log", "payload": "{}"})
    await mgr.broadcast_event(1, {"id": 7, "type": "log", "payload": "{}"})
    await mgr.broadcast_event(1, {"type": "status", "payload": "{}"})  # unpersisted events have no id

    assert ws.send_text.await_count == 2


@pytest.mark.asyncio
async def test_stalled_socket_does_not_block_other_listeners():
    async def hang(_):
        await asyncio.sleep(30)

    mgr = ConnectionManager(send_timeout=0.1)
    stalled, healthy = _socket(AsyncMock(side_effect=hang)), _socket()
    mgr.register(stalled, 1)
    mgr.register(healthy, 1)

    await asyncio.wait_for(mgr.broadcast_event(1, {"id": 1, "type": "log", "payload": "{}"}), timeout=2)

    healthy.send_text.assert_awaited_once()
    assert mgr.active_connections[1] == [healthy]


# --- Redis relay (multi-replica fan-out) ---

@pytest.mark.asyncio
async def test_redis_relay_forwards_events_and_reconnects_with_backoff():
    calls = {"n": 0}

    async def subscribe_all():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("redis down")
            yield  # pragma: no cover
        yield {"task_id": 3, "id": 11, "type": "log", "payload": "{}", "timestamp": "t"}
        raise asyncio.CancelledError

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    with patch("app.main.event_bus.subscribe_all", subscribe_all), \
         patch("app.main.manager.broadcast_event", new_callable=AsyncMock) as broadcast:
        with pytest.raises(asyncio.CancelledError):
            await relay_redis_events(sleep=fake_sleep)

    assert sleeps == [1]
    broadcast.assert_awaited_once_with(3, {"id": 11, "type": "log", "payload": "{}", "timestamp": "t"})


@pytest.mark.asyncio
async def test_event_bus_subscribe_all_uses_pattern_subscription():
    from app.events import RedisEventBus

    bus = RedisEventBus()
    pubsub = MagicMock()
    pubsub.psubscribe = AsyncMock()
    pubsub.punsubscribe = AsyncMock()
    pubsub.aclose = AsyncMock()
    pubsub.get_message = AsyncMock(side_effect=[
        None,
        {"type": "pmessage", "data": json.dumps({"task_id": 1, "id": 2})},
        asyncio.CancelledError(),
    ])
    bus._redis = MagicMock()
    bus._redis.pubsub.return_value = pubsub

    received = []
    with pytest.raises(asyncio.CancelledError):
        async for event in bus.subscribe_all():
            received.append(event)

    pubsub.psubscribe.assert_awaited_once_with("nimbus:events:task:*")
    assert received == [{"task_id": 1, "id": 2}]
    pubsub.aclose.assert_awaited()


@pytest.mark.asyncio
async def test_worker_events_carry_persisted_id():
    from app.worker import log_event

    db = AsyncMock()
    db.add = MagicMock()

    async def assign_id(ev):
        ev.id = 42

    db.refresh = AsyncMock(side_effect=assign_id)
    with patch("app.worker.event_bus.publish_event", new_callable=AsyncMock) as publish, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post:
        await log_event(db, 1, EventType.LOG, {"message": "hi"})

    assert publish.call_args.kwargs["event_id"] == 42
    assert post.call_args.kwargs["json"]["id"] == 42
