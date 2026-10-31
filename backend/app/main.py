from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Request, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text
from pydantic import BaseModel, field_validator
from typing import Optional, Dict
import json
import asyncio
import datetime
import logging
import time
import httpx
from collections import OrderedDict
from contextlib import asynccontextmanager

from .db import get_db, engine, Base, async_session
from .events import event_bus
from .models import User, Task, TaskEvent, TaskMessage, TaskStatus, EventType
from .worker import enqueue_task
from .auth import router as auth_router, get_optional_user, decode_access_token
from .credentials import router as credentials_router, user_router
from .model_prefs import router as model_prefs_router
from .security import (
    decrypt_secret,
    verify_internal_api_token,
    create_stream_ticket,
    verify_stream_ticket,
    STREAM_TICKET_TTL,
)
from .ratelimit import check_task_submission_limits
from .branches import validate_task_branch
from .settings import settings
from .logging_config import configure_logging, new_request_id, request_id_var

configure_logging()
logger = logging.getLogger(__name__)

HEALTH_PATHS = {"/", "/healthz", "/api/health"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup and graceful shutdown of async resources."""
    try:
        async with engine.begin() as conn:
            # Create all tables if they don't exist
            await conn.run_sync(Base.metadata.create_all)
            # Ensure any missing columns from previous schemas exist in PostgreSQL
            if "sqlite" not in str(engine.url):
                try:
                    await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN DEFAULT FALSE;"))
                    await conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;"))
                    await conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS repo_url VARCHAR;"))
                    await conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS git_branch VARCHAR;"))
                    await conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS pr_url VARCHAR;"))
                    await conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS patch_diff TEXT;"))
                    await conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS base_sha VARCHAR(40);"))
                    await conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS pushed_sha VARCHAR(40);"))
                    await conn.execute(text("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS head_repo VARCHAR;"))
                    await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS model_prefs TEXT;"))
                except Exception as alter_err:
                    logger.warning("Column migration check failed: %s", alter_err)
    except Exception as e:
        logger.warning("Database schema initialization failed: %s", e)

    relay_task = asyncio.create_task(relay_redis_events())
    try:
        yield
    finally:
        relay_task.cancel()
        try:
            await relay_task
        except asyncio.CancelledError:
            pass
        await event_bus.close()

app = FastAPI(title="Nimbus Control Plane", lifespan=lifespan)

# Mount authentication and credential routers
app.include_router(auth_router)
app.include_router(credentials_router)
app.include_router(user_router)
app.include_router(model_prefs_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://nimbusagent.vercel.app",
        settings.FRONTEND_URL
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def request_context(request: Request, call_next):
    """Tags every log line of a request with its id and logs one access line with timing."""
    request_id = new_request_id(request.headers.get("X-Request-ID"))
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        logger.log(
            logging.DEBUG if request.url.path in HEALTH_PATHS else logging.INFO,
            "%s %s -> %s", request.method, request.url.path, status_code,
            extra={
                "event": "http_request",
                "method": request.method,
                "path": request.url.path,
                "status": status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            }
        )
        request_id_var.reset(token)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Full details go to the logs only; clients get an id to quote, never a traceback
    request_id = getattr(request.state, "request_id", None) or new_request_id()
    logger.error(
        "Unhandled error on %s %s", request.method, request.url.path,
        exc_info=exc, extra={"event": "unhandled_error", "request_id": request_id}
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
        headers={"X-Request-ID": request_id}
    )

@app.api_route("/", methods=["GET", "HEAD"])
@app.api_route("/healthz", methods=["GET", "HEAD"])
@app.api_route("/api/health", methods=["GET", "HEAD"])
async def health_check():
    """Lightweight keep-alive and health check endpoint for UptimeRobot / ping monitors (supports GET and HEAD)."""
    return {
        "status": "healthy",
        "service": "nimbus-control-plane",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

class TaskCreate(BaseModel):
    prompt: str
    repo_url: Optional[str] = None
    git_branch: Optional[str] = None

    @field_validator("repo_url")
    @classmethod
    def _blank_repo_is_none(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() or None if v else None

    @field_validator("git_branch")
    @classmethod
    def _check_branch(cls, v: Optional[str]) -> Optional[str]:
        return validate_task_branch(v)


SIGN_IN_FOR_REPO_TASKS = "Sign in with GitHub to run tasks against a repository."

class TaskCreateResponse(BaseModel):
    id: int
    status: str
    repo_url: Optional[str] = None
    git_branch: Optional[str] = None
    user_id: Optional[int] = None

class TaskResponse(BaseModel):
    id: int
    status: str
    prompt: str
    repo_url: Optional[str] = None
    git_branch: Optional[str] = None
    pr_url: Optional[str] = None
    patch_diff: Optional[str] = None
    user_id: Optional[int] = None

class TaskCancelResponse(BaseModel):
    id: int
    status: str
    message: str

@app.get("/api/repos")
async def list_user_repositories(
    user: Optional[User] = Depends(get_optional_user),
    username_override: Optional[str] = None
):
    """
    Dynamically fetches up to 100 repositories for the authenticated user or specified handle.
    If authenticated with GitHub OAuth, private and organization repositories are included.
    """
    token: Optional[str] = None
    target_username = username_override

    if user:
        if user.github_token:
            token = decrypt_secret(user.github_token)
        if not target_username:
            target_username = user.username

    # If no authenticated user and no override provided, return empty list
    if not target_username and not token:
        return []

    headers: Dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Nimbus-Control-Plane"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
        url = "https://api.github.com/user/repos?sort=updated&per_page=100"
    else:
        url = f"https://api.github.com/users/{target_username}/repos?sort=updated&per_page=100"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return [
                        {
                            "id": r["id"],
                            "name": r["name"],
                            "full_name": r["full_name"],
                            "html_url": r["html_url"],
                            "stargazers_count": r.get("stargazers_count", 0),
                            "language": r.get("language"),
                            "description": r.get("description"),
                            "private": r.get("private", False)
                        }
                        for r in data
                    ]
            return []
    except Exception as e:
        logger.warning("Failed to fetch repositories from GitHub: %s", e)
        return []

@app.post("/api/tasks", response_model=TaskCreateResponse)
async def create_task(
    req: TaskCreate,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    # Repo tasks clone and push with the user's own GitHub credentials, never a server token
    if req.repo_url and user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SIGN_IN_FOR_REPO_TASKS)

    # Enforce concurrency quotas and rate limits
    await check_task_submission_limits(user, db)

    try:
        user_id = user.id if user else None
        
        task = Task(
            user_id=user_id,
            prompt=req.prompt,
            repo_url=req.repo_url,
            git_branch=req.git_branch,
            status=TaskStatus.PENDING
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        
        task_id = task.id if task.id is not None else 1
        
        # Enqueue task to background worker
        try:
            await enqueue_task(task_id, req.prompt, req.repo_url, req.git_branch)
        except Exception as queue_err:
            logger.error("Failed to enqueue task %s: %s", task_id, queue_err)
        
        status_val = str(task.status.value).lower() if hasattr(task.status, "value") else str(task.status or "pending").lower()
        return TaskCreateResponse(
            id=task_id,
            status=status_val,
            repo_url=task.repo_url,
            git_branch=task.git_branch,
            user_id=user_id
        )
    except Exception as e:
        await db.rollback()
        err_msg = f"Task creation failed in DB: {e}"
        logger.exception("Task creation failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=err_msg)

@app.get("/api/tasks", response_model=list[TaskResponse])
async def list_tasks(
    limit: int = 10,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    query = select(Task)
    if user:
        query = query.where(Task.user_id == user.id)
    else:
        query = query.where(Task.user_id.is_(None))
    query = query.order_by(Task.created_at.desc()).limit(limit)
    result = await db.execute(query)
    tasks = result.scalars().all()
    return [
        TaskResponse(
            id=t.id,
            status=str(t.status.value).lower() if hasattr(t.status, "value") else str(t.status).lower(),
            prompt=t.prompt,
            repo_url=t.repo_url,
            git_branch=t.git_branch,
            pr_url=t.pr_url,
            patch_diff=t.patch_diff,
            user_id=t.user_id
        )
        for t in tasks
    ]

class StreamTicketResponse(BaseModel):
    ticket: Optional[str]
    expires_in: int


@app.post("/api/tasks/{task_id}/stream-ticket", response_model=StreamTicketResponse)
async def create_task_stream_ticket(
    task_id: int,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """Issues a short-lived ticket for the task's WebSocket, which can't see the frontend's cookie."""
    task = await db.get(Task, task_id)
    if not task or (task.user_id is not None and (user is None or task.user_id != user.id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    ttl = int(STREAM_TICKET_TTL.total_seconds())
    if task.user_id is None:
        return StreamTicketResponse(ticket=None, expires_in=ttl)  # anonymous tasks need no ticket
    return StreamTicketResponse(ticket=create_stream_ticket(user.id, task_id), expires_in=ttl)


@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    
    # Strictly enforce owner-only access for registered user tasks
    if task.user_id is not None and (user is None or task.user_id != user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    status_val = str(task.status.value).lower() if hasattr(task.status, "value") else str(task.status).lower()
    return TaskResponse(
        id=task.id,
        status=status_val,
        prompt=task.prompt,
        repo_url=task.repo_url,
        git_branch=task.git_branch,
        pr_url=task.pr_url,
        patch_diff=task.patch_diff,
        user_id=task.user_id
    )

@app.get("/api/tasks/{task_id}/events")
async def get_task_events(
    task_id: int,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    task_res = await db.execute(select(Task).where(Task.id == task_id))
    task = task_res.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.user_id is not None and (user is None or task.user_id != user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    result = await db.execute(select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.id))
    events = result.scalars().all()
    return [_event_message(ev) for ev in events]

@app.get("/api/tasks/{task_id}/screenshots")
async def get_task_screenshots(
    task_id: int,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieves all visual screenshot snapshots captured during task execution."""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.user_id is not None and (user is None or task.user_id != user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    events_res = await db.execute(
        select(TaskEvent)
        .where(TaskEvent.task_id == task_id)
        .order_by(TaskEvent.created_at)
    )
    events = events_res.scalars().all()
    screenshots = []
    for ev in events:
        try:
            payload = json.loads(ev.payload) if isinstance(ev.payload, str) else ev.payload
            if isinstance(payload, dict) and "screenshot" in payload:
                screenshots.append({
                    "id": ev.id,
                    "task_id": task_id,
                    "filename": payload.get("filename", "screenshot.png"),
                    "caption": payload.get("caption", "Visual snapshot"),
                    "data": payload["screenshot"],
                    "created_at": ev.created_at.isoformat() + "Z" if ev.created_at else ""
                })
        except Exception:
            pass
    return screenshots

@app.post("/api/tasks/{task_id}/cancel", response_model=TaskCancelResponse)
async def cancel_task(
    task_id: int,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    
    if task.user_id is not None and (user is None or task.user_id != user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    
    if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
        return TaskCancelResponse(id=task.id, status=str(task.status.value).lower(), message="Task already in terminal state")

    task.status = TaskStatus.CANCELLED
    await db.commit()
    
    # Broadcast cancellation event
    cancel_payload = {
        "type": "status",
        "payload": json.dumps({"status": "cancelled"}),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    await manager.broadcast_event(task_id, cancel_payload)
    
    return TaskCancelResponse(id=task.id, status="cancelled", message="Task cancelled successfully")

async def _load_rerunnable_task(task_id: int, user: Optional[User], db: AsyncSession) -> Task:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.user_id is not None and (user is None or task.user_id != user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    # Anonymous repo tasks created before sign-in was required cannot be re-run
    if task.repo_url and task.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SIGN_IN_FOR_REPO_TASKS)
    return task


async def _requeue(task: Task, db: AsyncSession, log_message: str):
    task.status = TaskStatus.PENDING
    await db.commit()

    db.add(TaskEvent(
        task_id=task.id,
        event_type=EventType.LOG,
        payload=json.dumps({"message": log_message})
    ))
    await db.commit()

    await manager.broadcast_event(task.id, {
        "type": "status",
        "payload": json.dumps({"status": "pending"}),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    })
    await enqueue_task(task.id, task.prompt, task.repo_url, task.git_branch)


@app.post("/api/tasks/{task_id}/retry")
async def retry_task(
    task_id: int,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """Starts the task over from a fresh checkout, with the original prompt and every follow-up.

    The branch, PR and last pushed commit are kept, so the new result replaces the old one on the
    same branch and PR instead of failing on an existing branch.
    """
    task = await _load_rerunnable_task(task_id, user, db)
    if task.user_id is None:
        await check_task_submission_limits(None, db)

    task.patch_diff = None
    task.base_sha = None
    await _requeue(task, db, "🔄 Task restarted by user. Relaunching agent reasoning loop...")
    return {"id": task.id, "status": "pending", "message": "Task re-queued successfully"}


class FollowUpCreate(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Follow-up message is empty.")
        if len(v) > 10_000:
            raise ValueError("Follow-up message is longer than 10,000 characters.")
        return v


@app.post("/api/tasks/{task_id}/messages")
async def send_follow_up(
    task_id: int,
    req: FollowUpCreate,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """Continues a finished task: same task, same branch and PR, building on its current changes."""
    task = await _load_rerunnable_task(task_id, user, db)
    if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This task is still running. Wait for it to finish or stop it before sending a follow-up."
        )
    await check_task_submission_limits(user if task.user_id is not None else None, db)

    db.add(TaskMessage(task_id=task.id, content=req.message))
    await _requeue(task, db, f"💬 Follow-up: {req.message}")
    return {"id": task.id, "status": "pending", "message": "Follow-up queued on this task"}

@app.delete("/api/tasks/{task_id}")
async def delete_task(
    task_id: int,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    
    if task.user_id is not None and (user is None or task.user_id != user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    
    await db.delete(task)
    await db.commit()
    return {"ok": True, "message": f"Task #{task_id} deleted"}

@app.delete("/api/tasks")
async def clear_all_tasks(
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import delete
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    # Delete only tasks belonging to this user
    user_tasks = await db.execute(select(Task.id).where(Task.user_id == user.id))
    task_ids = user_tasks.scalars().all()
    if task_ids:
        await db.execute(delete(TaskEvent).where(TaskEvent.task_id.in_(task_ids)))
        await db.execute(delete(TaskMessage).where(TaskMessage.task_id.in_(task_ids)))
        await db.execute(delete(Task).where(Task.id.in_(task_ids)))
    await db.commit()
    return {"ok": True, "message": "Tasks cleared successfully"}

class ConnectionManager:
    """Per-process registry of live task streams.

    Events can reach a process twice (Redis pub/sub and the worker's HTTP fallback), so persisted
    events are de-duplicated by id. A socket that errors or stalls is dropped instead of blocking
    delivery to everyone else.
    """

    def __init__(self, send_timeout: float = 5.0, recent_ids_per_task: int = 1000):
        self.active_connections: dict[int, list[WebSocket]] = {}
        self.send_timeout = send_timeout
        self.recent_ids_per_task = recent_ids_per_task
        self._recent_ids: dict[int, "OrderedDict[int, None]"] = {}

    def register(self, websocket: WebSocket, task_id: int):
        self.active_connections.setdefault(task_id, []).append(websocket)

    def disconnect(self, websocket: WebSocket, task_id: int):
        if task_id in self.active_connections:
            if websocket in self.active_connections[task_id]:
                self.active_connections[task_id].remove(websocket)
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]
                self._recent_ids.pop(task_id, None)

    def _is_duplicate(self, task_id: int, event_id: Optional[int]) -> bool:
        if event_id is None:
            return False
        seen = self._recent_ids.setdefault(task_id, OrderedDict())
        if event_id in seen:
            return True
        seen[event_id] = None
        if len(seen) > self.recent_ids_per_task:
            seen.popitem(last=False)
        return False

    async def broadcast_event(self, task_id: int, event_data: dict):
        if task_id not in self.active_connections:
            return
        if self._is_duplicate(task_id, event_data.get("id")):
            return
        message = json.dumps(event_data)
        for connection in list(self.active_connections.get(task_id, [])):
            try:
                await asyncio.wait_for(connection.send_text(message), timeout=self.send_timeout)
            except Exception:
                self.disconnect(connection, task_id)

manager = ConnectionManager()


def _event_message(ev: TaskEvent) -> dict:
    return {
        "id": ev.id,
        "type": str(ev.event_type.value).lower() if hasattr(ev.event_type, "value") else str(ev.event_type).lower(),
        "payload": ev.payload,
        "timestamp": ev.created_at.isoformat() + "Z"
    }


async def relay_redis_events(sleep=asyncio.sleep):
    """Forwards worker events from Redis pub/sub to this process's sockets, reconnecting with backoff."""
    backoff = 1
    while True:
        try:
            async for data in event_bus.subscribe_all():
                backoff = 1
                task_id = data.get("task_id")
                if task_id is None:
                    continue
                await manager.broadcast_event(
                    int(task_id),
                    {key: data[key] for key in ("id", "type", "payload", "timestamp") if key in data}
                )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Redis event relay lost its subscription (%s); retrying in %ss", e, backoff)
            await sleep(backoff)
            backoff = min(backoff * 2, 30)


@app.websocket("/ws/tasks/{task_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    task_id: int,
    ticket: Optional[str] = Query(None, description="From POST /api/tasks/{id}/stream-ticket"),
    after: Optional[int] = Query(None, description="Resume cursor: only replay events with a larger id")
):
    # Accept before rejecting: a pre-accept close reaches browsers as 1006, hiding the 1008 auth code
    await websocket.accept()

    # Short-lived session: a long-lived stream must not pin a pooled DB connection
    async with async_session() as db:
        task = await db.get(Task, task_id)
    if not task:
        await websocket.close(code=1008, reason="Task not found")
        return

    if task.user_id is not None:
        # A ticket when connecting cross-origin; the session cookie when the API is same-origin (local dev)
        allowed_user = verify_stream_ticket(ticket, task_id)
        if allowed_user is None:
            cookie = websocket.cookies.get("nimbus_session")
            payload = decode_access_token(cookie) if cookie else None
            if payload and not payload.get("purpose"):
                allowed_user = payload.get("sub")
        if allowed_user != str(task.user_id):
            await websocket.close(code=1008, reason="Unauthorized access to task stream")
            return

    # Register before reading history so nothing published in between is missed (clients de-dupe by id)
    manager.register(websocket, task_id)
    try:
        async with async_session() as db:
            query = select(TaskEvent).where(TaskEvent.task_id == task_id)
            if after is not None:
                query = query.where(TaskEvent.id > after)
            result = await db.execute(query.order_by(TaskEvent.id))
            events = result.scalars().all()
        for ev in events:
            await websocket.send_text(json.dumps(_event_message(ev)))

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, task_id)

# API endpoint to post a new event (called by worker or redis listener)
@app.post("/api/internal/tasks/{task_id}/events")
async def post_event(
    task_id: int,
    payload: dict,
    x_nimbus_internal_token: Optional[str] = Header(None)
):
    if not verify_internal_api_token(x_nimbus_internal_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal token")
    # Broadcast real-time to active listeners
    await manager.broadcast_event(task_id, payload)
    return {"ok": True}
