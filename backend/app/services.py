"""Business rules: eligibility, deadlines, the application workflow, the offer limit, interviews and notifications.

Raises ApiError(status, message); the HTTP layer turns it into a JSON response.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone

from psycopg import Connection, errors

from . import repository as repo
from .db import transaction

IST = timezone(timedelta(hours=5, minutes=30), "IST")  # India has no daylight saving, so a fixed offset is exact

# allowed status changes (anything else is rejected with 409)
TRANSITIONS: dict[str, set[str]] = {
    "applied": {"shortlisted", "rejected", "withdrawn"},
    "shortlisted": {"interview", "rejected", "withdrawn"},
    "interview": {"offered", "rejected"},
    "offered": set(),
    "rejected": set(),
    "withdrawn": set(),
}
STUDENT_ALLOWED = {"withdrawn"}  # the only status a student may set on their own application

# what the student is told when someone else moves their application
STATUS_MESSAGES = {
    "shortlisted": "You have been shortlisted for {job}.",
    "interview": "You are through to the interview round for {job}.",
    "offered": "Congratulations! You have an offer for {job}.",
    "rejected": "Your application for {job} was not taken forward this time.",
    "withdrawn": "Your application for {job} was withdrawn by the placement office.",
}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _today() -> date:
    return date.today()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _constraint(e: errors.UniqueViolation) -> str:
    return e.diag.constraint_name or ""


# ------------------------------------------------------------------ students
def create_student(c: Connection, data: dict) -> dict:
    """Officer-created student (no login): creates the student and an API key in one transaction."""
    from .security import new_student_key  # local import: security depends on this module

    try:
        with transaction(c):
            sid = repo.insert_student(c, data)
            key = new_student_key(c, sid)
    except errors.UniqueViolation as e:
        field = "email" if "email" in _constraint(e) else "roll_no" if "roll_no" in _constraint(e) else "record"
        raise ApiError(409, f"a student with this {field} already exists") from None
    return {**repo.get_student(c, sid), "api_key": key}


def register_student(c: Connection, data: dict, password_hash: str) -> int:
    """Self-registration: the student row and the login are created together or not at all."""
    try:
        with transaction(c):
            sid = repo.insert_student(c, {**data, "cgpa": None})
            repo.insert_user(c, data["email"], password_hash, "student", sid)
    except errors.UniqueViolation as e:
        field = "roll number" if "roll_no" in _constraint(e) else "email"
        raise ApiError(409, f"an account with this {field} already exists") from None
    return sid


def get_student(c: Connection, sid: int) -> dict:
    s = repo.get_student(c, sid)
    if not s:
        raise ApiError(404, "student not found")
    return s


def update_student(c: Connection, sid: int, fields: dict) -> dict:
    get_student(c, sid)
    if fields:
        with transaction(c):
            repo.update_student(c, sid, fields)
    return repo.get_student(c, sid)


def delete_student(c: Connection, sid: int) -> None:
    with transaction(c):
        if not repo.delete_student(c, sid):
            raise ApiError(404, "student not found")


# ------------------------------------------------------------------ companies & jobs
def create_company(c: Connection, data: dict) -> dict:
    try:
        with transaction(c):
            cid = repo.insert_company(c, data)
    except errors.UniqueViolation:
        raise ApiError(409, "a company with this name already exists") from None
    return {**repo.get_company(c, cid), "open_jobs": 0}


def create_job(c: Connection, data: dict) -> dict:
    if not repo.get_company(c, data["company_id"]):
        raise ApiError(404, "company not found")
    if data["deadline"] < _today():
        raise ApiError(422, "deadline must not be in the past")
    with transaction(c):
        jid = repo.insert_job(c, data)
    return repo.get_job(c, jid)


def get_job(c: Connection, jid: int) -> dict:
    j = repo.get_job(c, jid)
    if not j:
        raise ApiError(404, "job not found")
    return j


def close_job(c: Connection, jid: int) -> dict:
    get_job(c, jid)
    with transaction(c):
        repo.lock_job(c, jid)  # waits for in-flight applications to this job to finish
        repo.set_job_status(c, jid, "closed")
    return repo.get_job(c, jid)


def eligible_jobs(c: Connection, sid: int) -> list[dict]:
    s = get_student(c, sid)
    if s["cgpa"] is None:
        return []  # nothing is open to a student until the placement office has verified their CGPA
    return repo.eligible_jobs(c, s["branch"], s["cgpa"], _today())


def job_stats(c: Connection, jid: int) -> dict:
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
def history(c: Connection, aid: int) -> list[dict]:
    if not repo.get_application(c, aid):
        raise ApiError(404, "application not found")
    return repo.list_events(c, aid)


def get_application(c: Connection, aid: int) -> dict:
    a = repo.get_application_detail(c, aid)
    if not a:
        raise ApiError(404, "application not found")
    return a


def apply(c: Connection, sid: int, jid: int, actor: str = "system") -> dict:
    s = get_student(c, sid)
    get_job(c, jid)
    try:
        with transaction(c):
            j = repo.lock_job(c, jid, shared=True)  # the job cannot be closed while this application is written
            if j["status"] != "open":
                raise ApiError(409, "this job is closed")
            if j["deadline"] < _today():
                raise ApiError(409, "the application deadline has passed")
            job = repo.get_job(c, jid)
            if s["branch"] not in job["eligible_branches"]:
                raise ApiError(403, f"branch {s['branch']} is not eligible for this job")
            if s["cgpa"] is None:
                raise ApiError(403, "your CGPA has not been verified by the placement office yet")
            if s["cgpa"] < job["min_cgpa"]:
                raise ApiError(403, f"CGPA {s['cgpa']:g} is below the minimum {job['min_cgpa']:g}")
            aid = repo.insert_application(c, sid, jid)
            repo.insert_event(c, aid, None, "applied", actor)
    except errors.UniqueViolation:
        # the database constraint one_application_per_job holds even when two requests arrive together
        raise ApiError(409, "already applied to this job") from None
    return repo.get_application_detail(c, aid)


def change_status(c: Connection, aid: int, new: str, actor: str = "system", student_id: int | None = None) -> dict:
    """student_id set = the caller is that student (may only withdraw their own application).

    Race safety: the job row is locked FOR UPDATE before anything is read, so two reviewers offering the last
    opening run one after the other; the second sees the first offer and gets 409. The status update is also
    compare-and-set (WHERE status = <what we read>)."""
    first = repo.get_application(c, aid)
    if not first:
        raise ApiError(404, "application not found")
    with transaction(c):
        repo.lock_job(c, first["job_id"])  # always lock the job first, then the application: one order, no deadlocks
        a = repo.get_application(c, aid, lock=True)
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
        job = repo.get_job(c, a["job_id"])
        if new == "offered" and repo.count_by_status(c, a["job_id"]).get("offered", 0) >= job["openings"]:
            raise ApiError(409, "all openings for this job already have offers")
        if not repo.update_application_status(c, aid, new, expected_old=old):
            raise ApiError(409, "the application changed while you were updating it; reload and retry")
        repo.insert_event(c, aid, old, new, actor)
        if student_id is None:  # someone else moved it: tell the student
            text = STATUS_MESSAGES[new].format(job=f"{job['title']} at {job['company_name']}")
            repo.insert_notification(c, a["student_id"], aid, f"status:{new}", text)
        if new == "offered" and repo.count_by_status(c, a["job_id"]).get("offered", 0) >= job["openings"]:
            repo.set_job_status(c, a["job_id"], "closed")  # last opening filled: stop new applications
    return repo.get_application_detail(c, aid)


# ------------------------------------------------------------------ interviews
def _clock(t: datetime) -> str:
    return t.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")


def schedule_interview(c: Connection, aid: int, data: dict, actor: str) -> dict:
    """Books (or moves) the interview slot for an application.

    Clash rules: a student cannot be in two interviews at once, and a panel cannot interview two students at once.
    Two officers booking at the same moment could both see "no clash" if we only checked; so the check and the
    write run under locks: the student's row (FOR UPDATE) and a per-panel advisory lock, always in that order."""
    starts: datetime = data["starts_at"]
    ends = starts + timedelta(minutes=data["duration_minutes"])
    if starts <= _now():
        raise ApiError(422, "the interview must be in the future")
    with transaction(c):
        a = repo.get_application(c, aid, lock=True)
        if not a:
            raise ApiError(404, "application not found")
        if a["status"] != "interview":
            raise ApiError(409, "move the application to the interview stage before scheduling")
        repo.get_student(c, a["student_id"], lock=True)
        c.execute("SELECT pg_advisory_xact_lock(hashtext(lower(%s)))", (data["panel"],))
        clashes = repo.overlapping_interviews(c, starts, ends, a["student_id"], data["panel"], aid)
        for x in clashes:
            span = f"{_clock(x['starts_at'])} to {x['ends_at'].astimezone(IST).strftime('%I:%M %p')}"
            if x["student_id"] == a["student_id"]:
                raise ApiError(409, f"the student already has an interview from {span}")
            raise ApiError(409, f"panel '{x['panel']}' is already interviewing from {span}")
        repo.upsert_interview(c, aid, a["student_id"], starts, ends, data["mode"], data["location"], data["panel"], actor)
        job = repo.get_job(c, a["job_id"])
        where = "online" if data["mode"] == "online" else (data["location"] or "on campus")
        repo.insert_notification(
            c, a["student_id"], aid, "interview",
            f"Interview for {job['title']} at {job['company_name']}: {_clock(starts)} ({where}).",
        )
    return repo.get_interview(c, aid)


def cancel_interview(c: Connection, aid: int) -> None:
    with transaction(c):
        a = repo.get_application(c, aid)
        if not a or not repo.delete_interview(c, aid):
            raise ApiError(404, "no interview is scheduled for this application")
        job = repo.get_job(c, a["job_id"])
        repo.insert_notification(c, a["student_id"], aid, "interview", f"Your interview for {job['title']} at {job['company_name']} was cancelled; a new time will follow.")


# ------------------------------------------------------------------ dashboard & export
def overview(c: Connection) -> dict:
    o = repo.overview(c, _now())
    o["placement_rate"] = round(o["placed_students"] / o["students"], 3) if o["students"] else 0.0
    return o


def _cell(v) -> str:
    """Spreadsheet apps run cells that start with = + - @ as formulas ("CSV injection"); prefix them with '."""
    s = ", ".join(v) if isinstance(v, list) else "" if v is None else v.isoformat() if isinstance(v, datetime) else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def applicants_csv(c: Connection, jid: int) -> str:
    get_job(c, jid)
    rows = repo.applicants_for_export(c, jid)
    cols = ["application_id", "name", "email", "roll_no", "branch", "cgpa", "skills", "status", "applied_at", "interview_at", "panel"]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(cols)
    for r in rows:
        w.writerow([_cell(r[k]) for k in cols])
    return out.getvalue()
