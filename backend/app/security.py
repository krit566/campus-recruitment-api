"""Authentication and role checks.

Two ways to sign a request:
- Web app: `Authorization: Bearer <JWT>` after logging in with email + password. Passwords are stored as bcrypt
  hashes; the token is signed with JWT_SECRET and expires after JWT_HOURS (default 8).
- Programs: `X-API-Key`. The officer key comes from RECRUIT_ADMIN_KEY; a student key is created when the officer adds
  a student, returned ONCE, and stored only as a SHA-256 hash.

Officers may do everything; a student may read jobs, read their own profile and act on their own applications only.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header
from psycopg import Connection

from . import repository as repo
from .db import get_conn
from .services import ApiError

log = logging.getLogger("recruitment.security")


@dataclass(frozen=True)
class Principal:
    role: str  # "officer" or "student"
    student_id: int | None = None
    user_id: int | None = None

    @property
    def name(self) -> str:
        """Who appears in the audit trail."""
        if self.role == "student":
            return f"student:{self.student_id}"
        return f"officer:{self.user_id}" if self.user_id else "officer"


# ------------------------------------------------------------------ passwords
def _rounds() -> int:
    return int(os.environ.get("BCRYPT_ROUNDS", "12"))  # tests lower this to stay fast


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_rounds())).decode()


def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode()[:72], hashed.encode())


_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(rounds=4)).decode()


# ------------------------------------------------------------------ login lockout
# After MAX_FAILURES wrong passwords for one email within WINDOW seconds, that email is blocked for the rest of the
# window. Kept in memory: enough for one instance; several instances would share it in Redis or the database.
MAX_FAILURES, WINDOW = 5, 15 * 60
_failures: dict[str, deque] = defaultdict(deque)
_fail_lock = threading.Lock()


def _recent_failures(email: str) -> deque:
    q = _failures[email]
    while q and q[0] < time.monotonic() - WINDOW:
        q.popleft()
    return q


def reset_lockouts() -> None:
    with _fail_lock:
        _failures.clear()


def authenticate(c: Connection, email: str, password: str) -> dict:
    email = email.strip().lower()
    with _fail_lock:
        if len(_recent_failures(email)) >= MAX_FAILURES:
            raise ApiError(429, "too many failed attempts; try again in 15 minutes")
    user = repo.get_user_by_email(c, email)
    # check a dummy hash when the email is unknown, so the response time does not reveal which emails have accounts
    ok = check_password(password, user["password_hash"] if user else _DUMMY_HASH) and user is not None
    if not ok:
        with _fail_lock:
            _recent_failures(email).append(time.monotonic())
        raise ApiError(401, "wrong email or password")
    with _fail_lock:
        _failures.pop(email, None)
    repo.touch_login(c, user["id"])
    return user


# ------------------------------------------------------------------ tokens
_generated_secret = secrets.token_urlsafe(32)


def _secret() -> str:
    s = os.environ.get("JWT_SECRET")
    if not s:
        # fine for local development; in production set JWT_SECRET so tokens survive restarts and multiple instances
        return _generated_secret
    return s


def check_secret() -> None:
    """Called at startup: warns about a missing or short JWT_SECRET (HS256 needs at least 32 bytes of key)."""
    s = os.environ.get("JWT_SECRET", "")
    if not s:
        log.warning("JWT_SECRET is not set: using a random secret, so everyone is signed out on every restart")
    elif len(s.encode()) < 32:
        log.warning("JWT_SECRET is shorter than 32 bytes; use a long random value in production")


def _hours() -> int:
    return int(os.environ.get("JWT_HOURS", "8"))


def issue_token(user: dict) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    claims = {"sub": str(user["id"]), "role": user["role"], "sid": user["student_id"], "iat": now, "exp": now + timedelta(hours=_hours())}
    return jwt.encode(claims, _secret(), algorithm="HS256"), _hours() * 3600


def _from_token(token: str) -> Principal:
    try:
        # algorithms is fixed: a token cannot pick "none" or another algorithm for itself
        claims = jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "your session has expired; please sign in again") from None
    except jwt.InvalidTokenError:
        raise ApiError(401, "invalid token") from None
    return Principal(claims["role"], claims.get("sid"), int(claims["sub"]))


# ------------------------------------------------------------------ API keys
def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_student_key(c: Connection, student_id: int) -> str:
    key = "stu_" + secrets.token_urlsafe(24)
    repo.insert_api_key(c, hash_key(key), "student", student_id)
    return key


# ------------------------------------------------------------------ FastAPI dependencies
def current_principal(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    c: Connection = Depends(get_conn),
) -> Principal:
    if authorization and authorization.lower().startswith("bearer "):
        return _from_token(authorization[7:].strip())
    if not x_api_key:
        raise ApiError(401, "sign in, or send an X-API-Key header")
    admin = os.environ.get("RECRUIT_ADMIN_KEY", "")
    if admin and hmac.compare_digest(x_api_key, admin):  # constant-time compare: no timing hints about the key
        return Principal("officer")
    row = repo.get_api_key(c, hash_key(x_api_key))
    if not row:
        raise ApiError(401, "invalid API key")
    return Principal(row["role"], row["student_id"])


def require_officer(p: Principal = Depends(current_principal)) -> Principal:
    if p.role != "officer":
        raise ApiError(403, "placement officer only")
    return p


def require_student(p: Principal = Depends(current_principal)) -> Principal:
    if p.role != "student":
        raise ApiError(403, "students only")
    return p


def require_self_or_officer(p: Principal, student_id: int) -> None:
    if p.role != "officer" and p.student_id != student_id:
        raise ApiError(403, "students can only access their own records")


def bootstrap_officer(c: Connection) -> None:
    """Creates the first officer login from RECRUIT_OFFICER_EMAIL / RECRUIT_OFFICER_PASSWORD when none exists
    (used on a fresh deployment). Does nothing once an officer exists."""
    email = os.environ.get("RECRUIT_OFFICER_EMAIL", "").strip().lower()
    password = os.environ.get("RECRUIT_OFFICER_PASSWORD", "")
    if not email or not password or repo.count_officers(c):
        return
    if len(password) < 12:
        log.warning("RECRUIT_OFFICER_PASSWORD is shorter than 12 characters; officer account not created")
        return
    repo.insert_user(c, email, hash_password(password), "officer", None)
    log.info("created the first officer account for %s", email)
