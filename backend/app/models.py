from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum
import datetime
from .db import Base


def utc_now():
    """Returns current UTC timestamp without timezone offset for naive DateTime columns."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class TaskStatus(str, enum.Enum):
    """Lifecycle states of an autonomous agent task (matching PostgreSQL enum definition)."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class EventType(str, enum.Enum):
    """Types of events logged in the append-only task event stream (matching PostgreSQL enum definition)."""
    LOG = "LOG"
    COMMAND = "COMMAND"
    RESULT = "RESULT"
    STATUS = "STATUS"


class Task(Base):
    """Database model representing a delegated coding task."""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    prompt = Column(Text, nullable=False)
    repo_url = Column(String, nullable=True)
    git_branch = Column(String, nullable=True)
    pr_url = Column(String, nullable=True)
    patch_diff = Column(Text, nullable=True)
    status = Column(Enum(TaskStatus, name="taskstatus"), default=TaskStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    events = relationship("TaskEvent", back_populates="task", cascade="all, delete-orphan")


class TaskEvent(Base):
    """Immutable, append-only event record for task execution history and live streaming."""
    __tablename__ = "task_events"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    event_type = Column(Enum(EventType, name="eventtype"), nullable=False)
    payload = Column(Text, nullable=False)  # JSON-encoded string
    created_at = Column(DateTime, default=utc_now)

    task = relationship("Task", back_populates="events")
