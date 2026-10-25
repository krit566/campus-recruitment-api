"""Business rules: eligibility, deadlines, the application status workflow and the offer limit.

Raises ApiError(status, message); the HTTP layer turns it into a JSON response.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from . import repository as repo
from .db import transaction

# allowed status changes (anything else is rejected with 409)
TRANSITIONS: dict[str, set[str]] = {
    "applied": {"shortlisted", "rejected", "withdrawn"},
    "shortlisted": {"interview", "rejected", "withdrawn"},
    "interview": {"offered", "rejected"},
    "offered": set(),
    "rejected": set(),
    "withdrawn": set(),
}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _today() -> str:
    return date.today().isoformat()


# ------------------------------------------------------------------ students
def create_student(c: sqlite3.Connection, data: dict) -> dict:
    """Creates the student and their API key in one transaction; the key is returned once and stored only hashed."""
    from .security import new_student_key  # local import: security depends on this module

    try:
        with transaction(c):
            sid = repo.insert_student(c, data)
            key = new_student_key(c, sid)
    except sqlite3.IntegrityError as e:
        field = "email" if "email" in str(e) else "roll_no" if "roll_no" in str(e) else "record"
        raise ApiError(409, f"a student with this {field} already exists") from None
    return {**repo.get_student(c, sid), "api_key": key}


def get_student(c: sqlite3.Connection, sid: int) -> dict:
    s = repo.get_student(c, sid)
    if not s:
        raise ApiError(404, "student not found")
    return s


def update_student(c: sqlite3.Connection, sid: int, fields: dict) -> dict:
    get_student(c, sid)
    if fields:
        with transaction(c):
            repo.update_student(c, sid, fields)
    return repo.get_student(c, sid)


def delete_student(c: sqlite3.Connection, sid: int) -> None:
    with transaction(c):
        if not repo.delete_student(c, sid):
            raise ApiError(404, "student not found")


# ------------------------------------------------------------------ companies & jobs
def create_company(c: sqlite3.Connection, data: dict) -> dict:
    try:
        with transaction(c):
            cid = repo.insert_company(c, data)
    except sqlite3.IntegrityError:
        raise ApiError(409, "a company with this name already exists") from None
    return repo.get_company(c, cid)


def create_job(c: sqlite3.Connection, data: dict) -> dict:
    if not repo.get_company(c, data["company_id"]):
        raise ApiError(404, "company not found")
    if data["deadline"] < _today():
        raise ApiError(422, "deadline must not be in the past")
    with transaction(c):
        jid = repo.insert_job(c, data)
    return repo.get_job(c, jid)


def get_job(c: sqlite3.Connection, jid: int) -> dict:
    j = repo.get_job(c, jid)
    if not j:
        raise ApiError(404, "job not found")
    return j


def close_job(c: sqlite3.Connection, jid: int) -> dict:
    get_job(c, jid)
    with transaction(c):
        repo.set_job_status(c, jid, "closed")
    return repo.get_job(c, jid)


def eligible_jobs(c: sqlite3.Connection, sid: int) -> list[dict]:
    s = get_student(c, sid)
    return repo.eligible_jobs(c, s["branch"], s["cgpa"], _today())


def job_stats(c: sqlite3.Connection, jid: int) -> dict:
    j = get_job(c, jid)
    counts = repo.count_by_status(c, jid)
    return {
        "job_id": jid,
        "openings": j["openings"],
        "total_applications": sum(counts.values()),
        "by_status": counts,
        "offers_left": j["openings"] - counts.get("offered", 0),
    }


# ------------------------------------------------------------------ applications
def history(c: sqlite3.Connection, aid: int) -> list[dict]:
    if not repo.get_application(c, aid):
        raise ApiError(404, "application not found")
    return repo.list_events(c, aid)


def apply(c: sqlite3.Connection, sid: int, jid: int, actor: str = "system") -> dict:
    s = get_student(c, sid)
    j = get_job(c, jid)
    if j["status"] != "open":
        raise ApiError(409, "this job is closed")
    if j["deadline"] < _today():
        raise ApiError(409, "the application deadline has passed")
    if s["branch"] not in j["eligible_branches"]:
        raise ApiError(403, f"branch {s['branch']} is not eligible for this job")
    if s["cgpa"] < j["min_cgpa"]:
        raise ApiError(403, f"CGPA {s['cgpa']} is below the minimum {j['min_cgpa']}")
    try:
        with transaction(c):
            aid = repo.insert_application(c, sid, jid)
            repo.insert_event(c, aid, None, "applied", actor)
    except sqlite3.IntegrityError:
        raise ApiError(409, "already applied to this job") from None
    return repo.get_application(c, aid)


STUDENT_ALLOWED = {"withdrawn"}  # the only status a student may set on their own application


def change_status(c: sqlite3.Connection, aid: int, new: str, actor: str = "system", student_id: int | None = None) -> dict:
    """student_id set = the caller is that student (may only withdraw their own application)."""
    with transaction(c):  # the read, the offer-limit check and the write happen under one write lock
        a = repo.get_application(c, aid)
        if not a:
            raise ApiError(404, "application not found")
        if student_id is not None:
            if a["student_id"] != student_id:
                raise ApiError(403, "students can only access their own records")
            if new not in STUDENT_ALLOWED:
                raise ApiError(403, "students can only withdraw their applications")
        old = a["status"]
        if new not in TRANSITIONS[old]:
            raise ApiError(409, f"cannot move an application from '{old}' to '{new}'")
        if new == "offered":
            j = repo.get_job(c, a["job_id"])
            if repo.count_by_status(c, a["job_id"]).get("offered", 0) >= j["openings"]:
                raise ApiError(409, "all openings for this job already have offers")
        if not repo.update_application_status(c, aid, new, expected_old=old):
            raise ApiError(409, "the application changed while you were updating it; reload and retry")
        repo.insert_event(c, aid, old, new, actor)
        if new == "offered":
            j = repo.get_job(c, a["job_id"])
            if repo.count_by_status(c, a["job_id"]).get("offered", 0) >= j["openings"]:
                repo.set_job_status(c, a["job_id"], "closed")  # last opening filled: stop new applications
    return repo.get_application(c, aid)
