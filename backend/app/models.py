from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum
import datetime
from .db import Base

class TaskStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class EventType(enum.Enum):
    LOG = "log"
    COMMAND = "command"
    RESULT = "result"
    STATUS = "status"

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    prompt = Column(Text, nullable=False)
    repo_url = Column(String, nullable=True)
    git_branch = Column(String, nullable=True)
    pr_url = Column(String, nullable=True)
    patch_diff = Column(Text, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    events = relationship("TaskEvent", back_populates="task", cascade="all, delete-orphan")

class TaskEvent(Base):
    __tablename__ = "task_events"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    event_type = Column(Enum(EventType), nullable=False)
    payload = Column(Text, nullable=False) # JSON string
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    task = relationship("Task", back_populates="events")
