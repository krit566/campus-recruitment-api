"""SQLite access: one connection per request, foreign keys on, schema created on startup.

Plain SQL (no ORM) on purpose: every query is visible and easy to explain.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    roll_no         TEXT NOT NULL UNIQUE,
    branch          TEXT NOT NULL,
    cgpa            REAL NOT NULL CHECK (cgpa >= 0 AND cgpa <= 10),
    graduation_year INTEGER NOT NULL,
    skills          TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS companies (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    website    TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS jobs (
    id                INTEGER PRIMARY KEY,
    company_id        INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    title             TEXT NOT NULL,
    description       TEXT NOT NULL DEFAULT '',
    min_cgpa          REAL NOT NULL DEFAULT 0 CHECK (min_cgpa >= 0 AND min_cgpa <= 10),
    eligible_branches TEXT NOT NULL,           -- comma-separated, e.g. 'CSE,IT'
    openings          INTEGER NOT NULL CHECK (openings > 0),
    deadline          TEXT NOT NULL,           -- ISO date
    status            TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS applications (
    id         INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    job_id     INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    status     TEXT NOT NULL DEFAULT 'applied',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (student_id, job_id)                -- one application per student per job
);

-- API keys: only the SHA-256 of a key is stored, never the key itself
CREATE TABLE IF NOT EXISTS api_keys (
    key_hash   TEXT PRIMARY KEY,
    role       TEXT NOT NULL CHECK (role IN ('officer', 'student')),
    student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- audit trail: every application status change, who made it and when
CREATE TABLE IF NOT EXISTS application_events (
    id             INTEGER PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    from_status    TEXT,
    to_status      TEXT NOT NULL,
    actor          TEXT NOT NULL,
    at             TEXT NOT NULL DEFAULT (datetime('now'))
);

-- idempotency: the first response to (caller, Idempotency-Key) is stored and replayed on retries
CREATE TABLE IF NOT EXISTS idempotency (
    principal   TEXT NOT NULL,
    key         TEXT NOT NULL,
    method      TEXT NOT NULL,
    path        TEXT NOT NULL,
    body_hash   TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    response    TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (principal, key)
);

CREATE INDEX IF NOT EXISTS ix_jobs_company ON jobs(company_id);
CREATE INDEX IF NOT EXISTS ix_apps_job_status ON applications(job_id, status);
CREATE INDEX IF NOT EXISTS ix_apps_student ON applications(student_id);
CREATE INDEX IF NOT EXISTS ix_events_app ON application_events(application_id);
"""


def db_path() -> str:
    return os.environ.get("RECRUIT_DB", "recruitment.db")


def connect(path: str | None = None) -> sqlite3.Connection:
    # check_same_thread=False: FastAPI may open the connection (dependency) and run the endpoint on different worker
    # threads. Safe here because each request owns its connection exclusively.
    # timeout: a writer waits up to 10 s for another writer's lock instead of failing with "database is locked".
    conn = sqlite3.connect(path or db_path(), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: str | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE takes the write lock up front, so check-then-write steps (e.g. 'is there an opening left?')
    cannot interleave with another writer."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def get_conn() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: a fresh connection per request, closed afterwards."""
    conn = connect()
    conn.isolation_level = None  # we manage transactions explicitly
    try:
        yield conn
    finally:
        conn.close()
