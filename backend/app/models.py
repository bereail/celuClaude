import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ActionDecision(str, Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


class ActionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXECUTED = "executed"
    FAILED = "failed"


class Device(Base):
    """A PC agent installation."""

    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    os: Mapped[str] = mapped_column(String, default="")
    token_hash: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="offline")  # online | offline
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cpu_percent: Mapped[float] = mapped_column(default=0.0)
    ram_percent: Mapped[float] = mapped_column(default=0.0)
    current_project: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    technologies: Mapped[str] = mapped_column(String, default="")  # comma-separated
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Session(Base):
    """A conversation / work session with Claude."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    title: Mapped[str] = mapped_column(String, default="")
    autonomy_level: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String, default="active")  # active | completed | failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[list["Message"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    actions: Mapped[list["ActionLog"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    role: Mapped[str] = mapped_column(String)  # user | assistant | activity
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    session: Mapped[Session] = relationship(back_populates="messages")


class ActionLog(Base):
    """Audit trail: every action Claude asked the agent to run."""

    __tablename__ = "action_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"))
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    tool_name: Mapped[str] = mapped_column(String)
    tool_input: Mapped[str] = mapped_column(Text)  # JSON
    decision: Mapped[str] = mapped_column(String)  # ActionDecision
    status: Mapped[str] = mapped_column(String, default=ActionStatus.PENDING.value)
    result: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped[Session] = relationship(back_populates="actions")


class StandingPermission(Base):
    """'Permitir siempre' grants recorded from an approval dialog."""

    __tablename__ = "standing_permissions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tool_name: Mapped[str] = mapped_column(String)
    pattern: Mapped[str] = mapped_column(String)  # e.g. command prefix or path glob
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
