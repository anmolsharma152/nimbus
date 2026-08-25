from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
import json
import asyncio
import datetime
import traceback
from contextlib import asynccontextmanager

from .db import get_db, engine, Base
from .models import Task, TaskEvent, TaskStatus, EventType
from .worker import enqueue_task

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "https://nimbusagent.vercel.app", "*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    err_trace = traceback.format_exc()
    print(f"[Unhandled Server Error on {request.url.path}]: {err_trace}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "trace": err_trace[:500]},
        headers={"Access-Control-Allow-Origin": "*"}
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
    try:
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
        try:
            await enqueue_task(task_id, req.prompt, req.repo_url, req.git_branch)
        except Exception as queue_err:
            print(f"Failed to enqueue task {task_id} into Redis: {queue_err}")
        
        status_val = str(task.status.value).lower() if hasattr(task.status, "value") else str(task.status or "pending").lower()
        return TaskCreateResponse(
            id=task_id,
            status=status_val,
            repo_url=task.repo_url,
            git_branch=task.git_branch
        )
    except Exception as e:
        await db.rollback()
        err_msg = f"Task creation failed in DB: {e}"
        print(f"Error in create_task: {traceback.format_exc()}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=err_msg)

@app.get("/api/tasks", response_model=list[TaskResponse])
async def list_tasks(limit: int = 10, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).order_by(Task.created_at.desc()).limit(limit))
    tasks = result.scalars().all()
    return [
        TaskResponse(
            id=t.id,
            status=str(t.status.value).lower() if hasattr(t.status, "value") else str(t.status).lower(),
            prompt=t.prompt,
            repo_url=t.repo_url,
            git_branch=t.git_branch,
            pr_url=t.pr_url,
            patch_diff=t.patch_diff
        )
        for t in tasks
    ]

@app.get("/api/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    status_val = str(task.status.value).lower() if hasattr(task.status, "value") else str(task.status).lower()
    return TaskResponse(
        id=task.id,
        status=status_val,
        prompt=task.prompt,
        repo_url=task.repo_url,
        git_branch=task.git_branch,
        pr_url=task.pr_url,
        patch_diff=task.patch_diff
    )

@app.get("/api/tasks/{task_id}/events")
async def get_task_events(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at))
    events = result.scalars().all()
    return [
        {
            "id": ev.id,
            "type": str(ev.event_type.value).lower() if hasattr(ev.event_type, "value") else str(ev.event_type).lower(),
            "payload": ev.payload,
            "timestamp": ev.created_at.isoformat()
        }
        for ev in events
    ]

@app.post("/api/tasks/{task_id}/cancel", response_model=TaskCancelResponse)
async def cancel_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
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
async def retry_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
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
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    
    await db.delete(task)
    await db.commit()
    return {"ok": True, "message": f"Task #{task_id} deleted"}

@app.delete("/api/tasks")
async def clear_all_tasks(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import delete
    await db.execute(delete(TaskEvent))
    await db.execute(delete(Task))
    await db.commit()
    return {"ok": True, "message": "All tasks cleared"}

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
        ev_type = str(ev.event_type.value).lower() if hasattr(ev.event_type, "value") else str(ev.event_type).lower()
        await websocket.send_text(json.dumps({
            "type": ev_type,
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
