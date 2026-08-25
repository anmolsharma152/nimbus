from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
import json
import asyncio

from .db import get_db
from .models import Task, TaskEvent, TaskStatus
from .worker import enqueue_task

app = FastAPI(title="Nimbus Control Plane")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TaskCreate(BaseModel):
    prompt: str
    repo_url: str | None = None
    git_branch: str | None = None

@app.post("/api/tasks")
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
    
    # Enqueue task to background worker
    await enqueue_task(task.id, req.prompt, req.repo_url, req.git_branch)
    
    status_val = task.status.value if hasattr(task.status, "value") else str(task.status or "pending")
    return {
        "id": task.id,
        "status": status_val,
        "repo_url": task.repo_url,
        "git_branch": task.git_branch
    }

@app.get("/api/tasks/{task_id}")
async def get_task(task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        return {"error": "Task not found"}
    return {
        "id": task.id,
        "status": task.status.value,
        "prompt": task.prompt,
        "repo_url": task.repo_url,
        "git_branch": task.git_branch,
        "pr_url": task.pr_url,
        "patch_diff": task.patch_diff
    }

# Simple in-memory connection manager for WebSockets
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
            self.active_connections[task_id].remove(websocket)

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
