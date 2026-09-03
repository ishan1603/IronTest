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
    """Create missing tables, then add any missing columns.

    Not a real migration tool -- it only ever ADDs. It will not alter or drop a
    column, and a destructive change still needs Alembic. But additive schema
    growth (a new nullable column) is the common case here, and this saves
    every existing local database from being deleted on each release.
    """
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    logger.info("Database ready at %s", _settings.database_url.split("@")[-1])


def _add_missing_columns() -> None:
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all just made it; it is current
            have = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in have:
                    continue
                if not (column.nullable or column.default is not None or column.server_default is not None):
                    logger.warning(
                        "Skipping non-nullable new column %s.%s; add it with a real migration.",
                        table.name,
                        column.name,
                    )
                    continue
                ddl = str(column.type.compile(dialect=engine.dialect))
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl}'))
                logger.info("Added column %s.%s", table.name, column.name)


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
