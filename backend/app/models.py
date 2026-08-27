from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum, Boolean, UniqueConstraint
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


class User(Base):
    """Database model representing an authenticated developer user."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    github_id = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    github_token = Column(Text, nullable=True)  # Encrypted at rest
    tier = Column(String, default="free", nullable=False)
    onboarding_completed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    credentials = relationship("UserCredential", back_populates="user", cascade="all, delete-orphan")


class UserCredential(Base):
    """Encrypted credential vault table storing per-user BYOK API keys and fine-grained tokens."""
    __tablename__ = "user_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(50), nullable=False)  # "gemini", "groq", "openrouter", "github_pat"
    encrypted_value = Column(Text, nullable=False)  # Fernet encrypted ciphertext
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="credentials")

    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_credential_provider"),
    )


class Task(Base):
    """Database model representing a delegated coding task."""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    prompt = Column(Text, nullable=False)
    repo_url = Column(String, nullable=True)
    git_branch = Column(String, nullable=True)
    pr_url = Column(String, nullable=True)
    patch_diff = Column(Text, nullable=True)
    status = Column(Enum(TaskStatus, name="taskstatus"), default=TaskStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="tasks")
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
