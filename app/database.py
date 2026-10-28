"""SQLAlchemy engine, session factory, declarative base and DB maintenance.

Durability defaults for the SQLite deployment:

* ``journal_mode=WAL`` — readers never block the writer, and a crash
  mid-write cannot corrupt the database file.
* ``synchronous=FULL`` (configurable) — a committed transaction survives a
  power cut.
* ``foreign_keys=ON`` — SQLite does not enforce foreign keys unless asked, so
  orphaned waveforms / measurements could otherwise accumulate.
* ``busy_timeout`` — concurrent users over the network wait for the write
  lock instead of failing with "database is locked".
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

log = logging.getLogger("app.database")

IS_SQLITE = settings.DATABASE_URL.startswith("sqlite")

_engine_kwargs = {"pool_pre_ping": True}  # transparently replace dead connections
if IS_SQLITE:
    _engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    if ":memory:" not in settings.DATABASE_URL and settings.DATABASE_URL != "sqlite://":
        _engine_kwargs.update(pool_size=settings.DB_POOL_SIZE,
                              max_overflow=settings.DB_MAX_OVERFLOW)
else:
    # Network database: recycle connections before server/firewall idle
    # timeouts silently drop them.
    _engine_kwargs.update(pool_size=settings.DB_POOL_SIZE,
                          max_overflow=settings.DB_MAX_OVERFLOW,
                          pool_recycle=1800)

engine = create_engine(settings.DATABASE_URL, **_engine_kwargs)

if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute(f"PRAGMA synchronous={settings.SQLITE_SYNCHRONOUS}")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.execute("PRAGMA cache_size=-20000")  # ~20 MB page cache
        cur.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def sqlite_path() -> Optional[Path]:
    """Filesystem path of the SQLite database, or None (memory / non-SQLite)."""
    if not IS_SQLITE:
        return None
    name = engine.url.database
    if not name or name == ":memory:":
        return None
    return Path(name).resolve()


def init_db():
    """Create tables, apply additive migrations and create missing indexes.

    When a migration would alter an existing table, a safety backup is taken
    first so a failed upgrade can always be rolled back.
    """
    from app import models  # noqa: F401

    pending = _missing_columns()
    if pending:
        log.warning("schema upgrade needed: %s", ", ".join(
            f"{t}.{c.name}" for t, c in pending))
        _pre_migration_backup()

    Base.metadata.create_all(bind=engine)
    _add_missing_columns(pending)
    _create_missing_indexes()


def _missing_columns() -> List[tuple]:
    inspector = inspect(engine)
    out = []
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {c["name"] for c in inspector.get_columns(table.name)}
        out.extend((table.name, c) for c in table.columns if c.name not in existing)
    return out


def _pre_migration_backup():
    from app import backup

    if not backup.supported():
        return
    try:
        info = backup.create_backup(tag="pre-migration")
        log.warning("pre-migration backup written: %s", info["name"])
    except backup.BackupError as e:
        # Never upgrade the schema without a safety copy.
        raise RuntimeError(f"Pre-migration backup failed, refusing to "
                           f"upgrade the database schema: {e}") from e


def _add_missing_columns(pending):
    """Lightweight migration: add model columns missing from existing tables
    (e.g. when the patient record grew). Only additive, nullable columns are
    handled.
    """
    for table_name, column in pending:
        col_type = column.type.compile(dialect=engine.dialect)
        with engine.begin() as conn:
            conn.execute(text(
                f'ALTER TABLE "{table_name}" ADD COLUMN '
                f'"{column.name}" {col_type}'
            ))


def _create_missing_indexes():
    """create_all() only builds indexes for new tables; add the ones declared
    later on tables that already exist (needed for speed as data grows)."""
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        existing = {ix["name"] for ix in inspector.get_indexes(table.name)}
        for index in table.indexes:
            if index.name not in existing:
                index.create(bind=engine)


# -- maintenance --------------------------------------------------------------

def optimize():
    """Refresh the query planner's statistics (cheap; keeps queries fast as
    tables grow)."""
    if IS_SQLITE:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA optimize")


def checkpoint():
    """Fold the WAL back into the main database file (on shutdown)."""
    if IS_SQLITE:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")


def quick_check() -> str:
    """Run SQLite's structural integrity check; returns 'ok' when healthy."""
    if not IS_SQLITE:
        return "unsupported"
    with engine.connect() as conn:
        rows = conn.exec_driver_sql("PRAGMA quick_check").fetchall()
    return "; ".join(r[0] for r in rows[:20])
