"""Postgres access: a small connection pool, explicit transactions, and migrations on startup.

Plain SQL (no ORM) on purpose: every query is visible and easy to explain. psycopg returns rows as dicts.

    DATABASE_URL=postgresql://user:password@host:5432/dbname
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (see .env.example)")
    # some hosts hand out postgres://; psycopg wants postgresql://
    return url.replace("postgres://", "postgresql://", 1)


def migrate(url: str | None = None) -> None:
    """Bring the schema up to date with Alembic (backend/migrations). Safe to run on every start: a Postgres advisory
    lock makes a second instance wait instead of running the same migration twice."""
    from alembic import command
    from alembic.config import Config

    url = url or database_url()
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("postgresql://", "postgresql+psycopg://", 1))
    with psycopg.connect(url, autocommit=True) as lock_conn:
        lock_conn.execute("SELECT pg_advisory_lock(424242)")
        try:
            command.upgrade(cfg, "head")
        finally:
            lock_conn.execute("SELECT pg_advisory_unlock(424242)")


def open_pool(url: str | None = None) -> None:
    global _pool
    close_pool()
    # autocommit: every statement commits on its own unless it runs inside `with transaction(conn):`
    _pool = ConnectionPool(
        url or database_url(),
        min_size=1,
        max_size=int(os.environ.get("DB_POOL_SIZE", "10")),
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=True,
    )


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def transaction(conn: psycopg.Connection) -> Iterator[psycopg.Connection]:
    """All statements inside commit together or not at all. Nested use becomes a SAVEPOINT, so a service can run
    inside a caller's transaction (the idempotency wrapper does this)."""
    with conn.transaction():
        yield conn


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    """A pooled connection outside a request (startup, scripts)."""
    if _pool is None:
        raise RuntimeError("database pool is not open")
    with _pool.connection() as conn:
        yield conn


def get_conn() -> Iterator[psycopg.Connection]:
    """FastAPI dependency: borrow a pooled connection for one request, return it afterwards."""
    if _pool is None:
        raise RuntimeError("database pool is not open")
    with _pool.connection() as conn:
        yield conn
