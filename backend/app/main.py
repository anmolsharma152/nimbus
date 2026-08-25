from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel, ConfigDict
from typing import Optional
import json
import asyncio
import datetime
from contextlib import asynccontextmanager

from .db import get_db
from .models import Task, TaskEvent, TaskStatus
from .worker import enqueue_task

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup and graceful shutdown of async resources."""
    yield

app = FastAPI(title="Nimbus Control Plane", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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

class TaskResponse(BaseModel):
    id: int
    status: str
    prompt: str
    repo_url: Optional[str] = None
    git_branch: Optional[str] = None
    pr_url: Optional[str] = None
    patch_diff: Optional[str] = None

class TaskCancelResponse(BaseModel):
    id: int
    status: str
    message: str

@app.post("/api/tasks", response_model=TaskCreateResponse)
async def create_task(req: TaskCreate, db: AsyncSession = Depends(get_db)):
    task = Task(
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
    await enqueue_task(task_id, req.prompt, req.repo_url, req.git_branch)
    
    status_val = task.status.value if hasattr(task.status, "value") else str(task.status or "pending")
    return TaskCreateResponse(
        id=task_id,
        status=status_val,
        repo_url=task.repo_url,
        git_branch=task.git_branch
    )

@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return TaskResponse(
        id=task.id,
        status=task.status.value,
        prompt=task.prompt,
        repo_url=task.repo_url,
        git_branch=task.git_branch,
        pr_url=task.pr_url,
        patch_diff=task.patch_diff
    )

@app.post("/api/tasks/{task_id}/cancel", response_model=TaskCancelResponse)
async def cancel_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    
    if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
        return TaskCancelResponse(id=task.id, status=task.status.value, message="Task already in terminal state")

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
async def websocket_endpoint(websocket: WebSocket, task_id: int, db: AsyncSession = Depends(get_db)):
    await manager.connect(websocket, task_id)
    
    # Send historical events first
    result = await db.execute(select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at))
    events = result.scalars().all()
    for ev in events:
        await websocket.send_text(json.dumps({
            "type": ev.event_type.value,
            "payload": ev.payload,
            "timestamp": ev.created_at.isoformat()
        }))

    try:
        while True:
            data = await websocket.receive_text()
            # We don't really expect much from the client in V1, but keep connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket, task_id)

# API endpoint to post a new event (could be called by worker or directly via redis pub/sub in the future)
@app.post("/api/internal/tasks/{task_id}/events")
async def post_event(task_id: int, payload: dict):
    # Broadcast it real-time to active listeners
    await manager.broadcast_event(task_id, payload)
    return {"ok": True}
