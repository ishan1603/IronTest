"""Engine, session factory, and schema bootstrap."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings, sqlite_path
from db.models import Base

logger = logging.getLogger(__name__)

_settings = get_settings()
_is_sqlite = _settings.database_url.startswith("sqlite")

if _is_sqlite:
    path = sqlite_path(_settings.database_url)
    if path:
        os.makedirs(os.path.dirname(path), exist_ok=True)

engine: Engine = create_engine(
    _settings.database_url,
    # SQLite's default check blocks the threadpool FastAPI runs sync work on.
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=not _is_sqlite,
    future=True,
)


if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _enable_sqlite_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        # WAL lets the SSE stream read while a run writes.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    """Create any missing tables.

    Sufficient while the schema only grows. A destructive change needs a real
    migration tool; this will not alter an existing column.
    """
    Base.metadata.create_all(bind=engine)
    logger.info("Database ready at %s", _settings.database_url.split("@")[-1])


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for background work outside a request."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
