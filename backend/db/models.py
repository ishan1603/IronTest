"""ORM models.

Every row that holds user data carries a user_id and is queried through it.
The previous JSON history file was global, so any visitor's run history was
visible to every other visitor; scoping is enforced at the schema level here
rather than left to callers to remember.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    github_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    login: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    avatar_url: Mapped[str | None] = mapped_column(String(500))

    #: GitHub OAuth token, Fernet-encrypted. Never returned by the API.
    encrypted_access_token: Mapped[str | None] = mapped_column(Text)
    token_scopes: Mapped[str] = mapped_column(String(400), default="")

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    repositories: Mapped[list["Repository"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    chats: Mapped[list["Chat"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    runs: Mapped[list["PipelineRun"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Repository(Base, TimestampMixin):
    """A GitHub repository the user has connected to IronTest."""

    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("user_id", "github_repo_id", name="uq_repo_per_user"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    github_repo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    full_name: Mapped[str] = mapped_column(String(300), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    private: Mapped[bool] = mapped_column(Boolean, default=False)
    default_branch: Mapped[str] = mapped_column(String(200), default="main")
    language: Mapped[str | None] = mapped_column(String(80))
    html_url: Mapped[str] = mapped_column(String(500), default="")

    #: Cached detection output: test framework, package manager, source roots.
    stack_profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="repositories")
    chats: Mapped[list["Chat"]] = relationship(back_populates="repository", cascade="all, delete-orphan")


class Chat(Base, TimestampMixin):
    """A conversation scoped to one repository."""

    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)

    title: Mapped[str] = mapped_column(String(300), default="New conversation")

    user: Mapped[User] = relationship(back_populates="chats")
    repository: Mapped[Repository] = relationship(back_populates="chats")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    runs: Mapped[list["PipelineRun"]] = relationship(back_populates="chat", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_chat_created", "chat_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)

    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, default="")
    #: "text" for prose, "run" when the message renders a pipeline result card.
    kind: Mapped[str] = mapped_column(String(30), default="text")
    run_id: Mapped[str | None] = mapped_column(String(32))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    chat: Mapped[Chat] = relationship(back_populates="messages")


class PipelineRun(Base, TimestampMixin):
    """One execution of the four-agent pipeline."""

    __tablename__ = "pipeline_runs"
    __table_args__ = (
        Index("ix_runs_user_created", "user_id", "created_at"),
        Index("ix_runs_repo_created", "repository_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    repository_id: Mapped[str | None] = mapped_column(
        ForeignKey("repositories.id", ondelete="SET NULL"), index=True
    )
    chat_id: Mapped[str | None] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), index=True)

    # queued | running | complete | failed
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    #: "existing_code" tests shipped behaviour; "specification" tests behaviour
    #: that is not built yet, where failures are the expected red phase.
    mode: Mapped[str] = mapped_column(String(30), default="existing_code")

    source: Mapped[str] = mapped_column(String(40), default="chat")
    story_text: Mapped[str] = mapped_column(Text, default="")
    #: Stable hash of the story, used to group runs for trend analysis.
    story_key: Mapped[str] = mapped_column(String(64), index=True, default="")
    story_label: Mapped[str] = mapped_column(String(300), default="")

    story_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    tests_result: Mapped[list[Any] | None] = mapped_column(JSON)
    execution_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    defects_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    fixes_result: Mapped[list[Any] | None] = mapped_column(JSON)

    total_tests: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    pass_rate: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_score: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    error_message: Mapped[str] = mapped_column(Text, default="")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="runs")
    chat: Mapped[Chat | None] = relationship(back_populates="runs")

    @property
    def executed_tests(self) -> int:
        return self.passed + self.failed + self.errors
