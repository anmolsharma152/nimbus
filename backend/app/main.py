from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
import asyncio
import datetime
import traceback
import httpx
from contextlib import asynccontextmanager

from .db import get_db, engine, Base
from .models import User, Task, TaskEvent, TaskStatus, EventType
from .worker import enqueue_task
from .auth import router as auth_router, get_current_user, get_optional_user, decode_access_token
from .credentials import router as credentials_router, user_router
from .security import decrypt_secret
from .ratelimit import check_task_submission_limits
from .settings import settings

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
                except Exception as alter_err:
                    print(f"Column migration check note: {alter_err}")
    except Exception as e:
        print(f"Database schema initialization notice: {e}")
    yield

app = FastAPI(title="Nimbus Control Plane", lifespan=lifespan)

# Mount authentication and credential routers
app.include_router(auth_router)
app.include_router(credentials_router)
app.include_router(user_router)

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

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    err_trace = traceback.format_exc()
    print(f"[Unhandled Server Error on {request.url.path}]: {err_trace}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "trace": err_trace[:500]}
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

    # If no authenticated user and no override provided, fallback to default showcase user
    if not target_username:
        target_username = "anmolsharma152"

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
        print(f"Failed to fetch repositories from GitHub: {e}")
        return []

@app.post("/api/tasks", response_model=TaskCreateResponse)
async def create_task(
    req: TaskCreate,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
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
            print(f"Failed to enqueue task {task_id} into Redis: {queue_err}")
        
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
        print(f"Error in create_task: {traceback.format_exc()}")
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

    result = await db.execute(select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at))
    events = result.scalars().all()
    return [
        {
            "id": ev.id,
            "type": str(ev.event_type.value).lower() if hasattr(ev.event_type, "value") else str(ev.event_type).lower(),
            "payload": ev.payload,
            "timestamp": ev.created_at.isoformat() + "Z"
        }
        for ev in events
    ]

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

@app.post("/api/tasks/{task_id}/retry")
async def retry_task(
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
    
    # Reset task state for fresh execution
    task.status = TaskStatus.PENDING
    task.patch_diff = None
    task.pr_url = None
    await db.commit()
    
    # Log restart event
    retry_event = TaskEvent(
        task_id=task.id,
        event_type=EventType.LOG,
        payload=json.dumps({"message": "🔄 Task restarted by user. Relaunching agent reasoning loop..."})
    )
    db.add(retry_event)
    await db.commit()
    
    # Broadcast status change to live WebSockets
    status_payload = {
        "type": "status",
        "payload": json.dumps({"status": "pending"}),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    await manager.broadcast_event(task_id, status_payload)
    
    # Re-enqueue task execution
    await enqueue_task(task.id, task.prompt, task.repo_url, task.git_branch)
    
    return {"id": task.id, "status": "pending", "message": "Task re-queued successfully"}

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
    if user:
        # Delete only tasks belonging to this user
        user_tasks = await db.execute(select(Task.id).where(Task.user_id == user.id))
        task_ids = user_tasks.scalars().all()
        if task_ids:
            await db.execute(delete(TaskEvent).where(TaskEvent.task_id.in_(task_ids)))
            await db.execute(delete(Task).where(Task.id.in_(task_ids)))
    else:
        await db.execute(delete(TaskEvent))
        await db.execute(delete(Task))
    await db.commit()
    return {"ok": True, "message": "Tasks cleared successfully"}

# Simple connection manager with leak prevention
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, task_id: int):
        await websocket.accept()
        if task_id not in self.active_connections:
            self.active_connections[task_id] = []
        self.active_connections[task_id].append(websocket)

    def disconnect(self, websocket: WebSocket, task_id: int):
        if task_id in self.active_connections:
            if websocket in self.active_connections[task_id]:
                self.active_connections[task_id].remove(websocket)
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]

    async def broadcast_event(self, task_id: int, event_data: dict):
        if task_id in self.active_connections:
            for connection in self.active_connections[task_id]:
                try:
                    await connection.send_text(json.dumps(event_data))
                except Exception:
                    pass

manager = ConnectionManager()

@app.websocket("/ws/tasks/{task_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    task_id: int,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    # Verify task existence and authorization
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        await websocket.close(code=1008, reason="Task not found")
        return

    # If task belongs to a registered user, verify session token
    if task.user_id is not None:
        auth_token = token or websocket.cookies.get("nimbus_session")
        if not auth_token:
            await websocket.close(code=1008, reason="Authentication required for this task")
            return
        payload = decode_access_token(auth_token)
        if not payload or payload.get("sub") != str(task.user_id):
            await websocket.close(code=1008, reason="Unauthorized access to task stream")
            return

    await manager.connect(websocket, task_id)
    
    # Send historical events first
    result = await db.execute(select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at))
    events = result.scalars().all()
    for ev in events:
        ev_type = str(ev.event_type.value).lower() if hasattr(ev.event_type, "value") else str(ev.event_type).lower()
        await websocket.send_text(json.dumps({
            "type": ev_type,
            "payload": ev.payload,
            "timestamp": ev.created_at.isoformat() + "Z"
        }))

    try:
        while True:
            data = await websocket.receive_text()
            # Keep connection open
    except WebSocketDisconnect:
        manager.disconnect(websocket, task_id)

# API endpoint to post a new event (called by worker or redis listener)
@app.post("/api/internal/tasks/{task_id}/events")
async def post_event(task_id: int, payload: dict):
    # Broadcast real-time to active listeners
    await manager.broadcast_event(task_id, payload)
    return {"ok": True}
