"""API-key authentication and role checks.

- The placement officer's key comes from the RECRUIT_ADMIN_KEY environment variable (never from the code).
- A student's key is generated when the officer creates the student, returned ONCE, and stored only as a SHA-256 hash.
- Officers may do everything; a student may read jobs, read their own profile and act on their own applications only.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from dataclasses import dataclass

from fastapi import Depends, Header

from .db import get_conn
from .services import ApiError


@dataclass(frozen=True)
class Principal:
    role: str  # "officer" or "student"
    student_id: int | None = None

    @property
    def name(self) -> str:
        return "officer" if self.role == "officer" else f"student:{self.student_id}"


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_student_key(c: sqlite3.Connection, student_id: int) -> str:
    key = "stu_" + secrets.token_urlsafe(24)
    c.execute("INSERT INTO api_keys (key_hash, role, student_id) VALUES (?, 'student', ?)", (hash_key(key), student_id))
    return key


def current_principal(x_api_key: str | None = Header(default=None), c: sqlite3.Connection = Depends(get_conn)) -> Principal:
    if not x_api_key:
        raise ApiError(401, "missing X-API-Key header")
    admin = os.environ.get("RECRUIT_ADMIN_KEY", "")
    if admin and hmac.compare_digest(x_api_key, admin):  # constant-time compare: no timing hints about the key
        return Principal("officer")
    row = c.execute("SELECT role, student_id FROM api_keys WHERE key_hash = ?", (hash_key(x_api_key),)).fetchone()
    if not row:
        raise ApiError(401, "invalid API key")
    return Principal(row["role"], row["student_id"])


def require_officer(p: Principal = Depends(current_principal)) -> Principal:
    if p.role != "officer":
        raise ApiError(403, "placement officer only")
    return p


def require_self_or_officer(p: Principal, student_id: int) -> None:
    if p.role != "officer" and p.student_id != student_id:
        raise ApiError(403, "students can only access their own records")
