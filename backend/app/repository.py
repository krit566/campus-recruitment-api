"""Repository layer: the only place that writes SQL. Returns plain dicts; knows nothing about HTTP or business rules.

Every value goes in as a query parameter (%s), never by string formatting, so user input cannot change a query.
"""

from __future__ import annotations

from datetime import date, datetime

from psycopg import Connection

Conn = Connection

STUDENT_COLS = "id, name, email, roll_no, branch, cgpa, graduation_year, skills, resume_name, resume_uploaded_at"
JOB_SELECT = """
    SELECT j.id, j.company_id, c.name AS company_name, j.title, j.description, j.location, j.ctc_lpa, j.min_cgpa,
           j.eligible_branches, j.openings, j.deadline, j.status,
           (SELECT COUNT(*) FROM applications a WHERE a.job_id = j.id) AS applications
    FROM jobs j JOIN companies c ON c.id = j.company_id
"""
APP_SELECT = """
    SELECT a.id, a.student_id, a.job_id, a.status, a.created_at, a.updated_at,
           s.name AS student_name, s.email AS student_email, s.roll_no, s.branch, s.cgpa,
           j.title AS job_title, c.name AS company_name, i.starts_at AS interview_at
    FROM applications a
    JOIN students s ON s.id = a.student_id
    JOIN jobs j ON j.id = a.job_id
    JOIN companies c ON c.id = j.company_id
    LEFT JOIN interviews i ON i.application_id = a.id
"""


def _one(c: Conn, sql: str, params: tuple | list = ()) -> dict | None:
    return c.execute(sql, params).fetchone()


def _all(c: Conn, sql: str, params: tuple | list = ()) -> list[dict]:
    return c.execute(sql, params).fetchall()


# ------------------------------------------------------------------ students
def insert_student(c: Conn, s: dict) -> int:
    return _one(
        c,
        "INSERT INTO students (name, email, roll_no, branch, cgpa, graduation_year, skills) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (s["name"], s["email"], s["roll_no"], s["branch"], s.get("cgpa"), s["graduation_year"], s["skills"]),
    )["id"]


def get_student(c: Conn, sid: int, lock: bool = False) -> dict | None:
    # FOR UPDATE: used while scheduling interviews, so two schedulers for one student wait for each other
    return _one(c, f"SELECT {STUDENT_COLS} FROM students WHERE id = %s" + (" FOR UPDATE" if lock else ""), (sid,))


def list_students(c: Conn, branch: str | None, min_cgpa: float | None, skill: str | None, q: str | None,
                  unverified: bool, limit: int, offset: int) -> tuple[list[dict], int]:
    where, params = ["TRUE"], []
    if branch:
        where.append("branch = %s")
        params.append(branch)
    if min_cgpa is not None:
        where.append("cgpa >= %s")
        params.append(min_cgpa)
    if skill:
        # whole-skill match, case-insensitive: "Java" does not match "JavaScript"
        where.append("EXISTS (SELECT 1 FROM unnest(skills) AS sk WHERE lower(sk) = lower(%s))")
        params.append(skill)
    if q:
        where.append("(name ILIKE %s OR email ILIKE %s OR roll_no ILIKE %s)")
        params += [f"%{q}%"] * 3
    if unverified:
        where.append("cgpa IS NULL")
    w = " AND ".join(where)
    total = _one(c, f"SELECT COUNT(*) AS n FROM students WHERE {w}", params)["n"]
    rows = _all(c, f"SELECT {STUDENT_COLS} FROM students WHERE {w} ORDER BY id LIMIT %s OFFSET %s", [*params, limit, offset])
    return rows, total


UPDATABLE_STUDENT_FIELDS = {"name", "cgpa", "skills"}


def update_student(c: Conn, sid: int, fields: dict) -> None:
    cols = [k for k in fields if k in UPDATABLE_STUDENT_FIELDS]  # column names come from this fixed set only
    if cols:
        sets = ", ".join(f"{k} = %s" for k in cols)
        c.execute(f"UPDATE students SET {sets} WHERE id = %s", [*(fields[k] for k in cols), sid])


def set_resume(c: Conn, sid: int, path: str, name: str) -> None:
    c.execute("UPDATE students SET resume_path = %s, resume_name = %s, resume_uploaded_at = now() WHERE id = %s", (path, name, sid))


def get_resume(c: Conn, sid: int) -> dict | None:
    return _one(c, "SELECT resume_path, resume_name FROM students WHERE id = %s AND resume_path IS NOT NULL", (sid,))


def delete_student(c: Conn, sid: int) -> bool:
    return c.execute("DELETE FROM students WHERE id = %s", (sid,)).rowcount > 0


# ------------------------------------------------------------------ users & keys
def insert_user(c: Conn, email: str, password_hash: str, role: str, student_id: int | None) -> int:
    return _one(
        c, "INSERT INTO users (email, password_hash, role, student_id) VALUES (%s, %s, %s, %s) RETURNING id",
        (email, password_hash, role, student_id),
    )["id"]


def get_user_by_email(c: Conn, email: str) -> dict | None:
    return _one(c, "SELECT id, email, password_hash, role, student_id FROM users WHERE email = %s", (email,))


def get_user(c: Conn, uid: int) -> dict | None:
    return _one(
        c, "SELECT u.id, u.email, u.role, u.student_id, s.name FROM users u LEFT JOIN students s ON s.id = u.student_id WHERE u.id = %s",
        (uid,),
    )


def touch_login(c: Conn, uid: int) -> None:
    c.execute("UPDATE users SET last_login_at = now() WHERE id = %s", (uid,))


def count_officers(c: Conn) -> int:
    return _one(c, "SELECT COUNT(*) AS n FROM users WHERE role = 'officer'")["n"]


def insert_api_key(c: Conn, key_hash: str, role: str, student_id: int | None) -> None:
    c.execute("INSERT INTO api_keys (key_hash, role, student_id) VALUES (%s, %s, %s)", (key_hash, role, student_id))


def get_api_key(c: Conn, key_hash: str) -> dict | None:
    return _one(c, "SELECT role, student_id FROM api_keys WHERE key_hash = %s", (key_hash,))


# ------------------------------------------------------------------ companies
def insert_company(c: Conn, co: dict) -> int:
    return _one(
        c, "INSERT INTO companies (name, website, industry) VALUES (%s, %s, %s) RETURNING id",
        (co["name"], co.get("website"), co.get("industry", "")),
    )["id"]


def get_company(c: Conn, cid: int) -> dict | None:
    return _one(c, "SELECT id, name, website, industry FROM companies WHERE id = %s", (cid,))


def list_companies(c: Conn) -> list[dict]:
    return _all(
        c,
        "SELECT c.id, c.name, c.website, c.industry, "
        "  (SELECT COUNT(*) FROM jobs j WHERE j.company_id = c.id AND j.status = 'open') AS open_jobs "
        "FROM companies c ORDER BY c.name",
    )


# ------------------------------------------------------------------ jobs
def insert_job(c: Conn, j: dict) -> int:
    return _one(
        c,
        "INSERT INTO jobs (company_id, title, description, location, ctc_lpa, min_cgpa, eligible_branches, openings, deadline) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (j["company_id"], j["title"], j["description"], j["location"], j["ctc_lpa"], j["min_cgpa"],
         [getattr(b, "value", b) for b in j["eligible_branches"]], j["openings"], j["deadline"]),  # enum -> "CSE"
    )["id"]


def get_job(c: Conn, jid: int) -> dict | None:
    return _one(c, JOB_SELECT + " WHERE j.id = %s", (jid,))


def lock_job(c: Conn, jid: int, shared: bool = False) -> dict | None:
    """Row lock on the job for the rest of the transaction.
    FOR UPDATE (offers): a second reviewer waits until the first has committed, then sees the new offer count.
    FOR SHARE (applying): many students may apply at once, but the job cannot be closed in the middle."""
    return _one(c, "SELECT id, openings, status, deadline FROM jobs WHERE id = %s " + ("FOR SHARE" if shared else "FOR UPDATE"), (jid,))


def list_jobs(c: Conn, status: str | None, company_id: int | None, branch: str | None, q: str | None,
              limit: int, offset: int) -> tuple[list[dict], int]:
    where, params = ["TRUE"], []
    if status:
        where.append("j.status = %s")
        params.append(status)
    if company_id:
        where.append("j.company_id = %s")
        params.append(company_id)
    if branch:
        where.append("%s = ANY(j.eligible_branches)")
        params.append(branch)
    if q:
        where.append("(j.title ILIKE %s OR c.name ILIKE %s OR j.location ILIKE %s)")
        params += [f"%{q}%"] * 3
    w = " AND ".join(where)
    total = _one(c, f"SELECT COUNT(*) AS n FROM jobs j JOIN companies c ON c.id = j.company_id WHERE {w}", params)["n"]
    rows = _all(c, JOB_SELECT + f" WHERE {w} ORDER BY j.deadline, j.id LIMIT %s OFFSET %s", [*params, limit, offset])
    return rows, total


def eligible_jobs(c: Conn, branch: str, cgpa: float, today: date) -> list[dict]:
    return _all(
        c,
        JOB_SELECT + " WHERE j.status = 'open' AND j.deadline >= %s AND j.min_cgpa <= %s AND %s = ANY(j.eligible_branches) "
        "ORDER BY j.deadline, j.id",
        (today, cgpa, branch),
    )


def set_job_status(c: Conn, jid: int, status: str) -> None:
    c.execute("UPDATE jobs SET status = %s WHERE id = %s", (status, jid))


# ------------------------------------------------------------------ applications
def insert_application(c: Conn, sid: int, jid: int) -> int:
    return _one(c, "INSERT INTO applications (student_id, job_id) VALUES (%s, %s) RETURNING id", (sid, jid))["id"]


def get_application(c: Conn, aid: int, lock: bool = False) -> dict | None:
    return _one(c, "SELECT * FROM applications WHERE id = %s" + (" FOR UPDATE" if lock else ""), (aid,))


def get_application_detail(c: Conn, aid: int) -> dict | None:
    return _one(c, APP_SELECT + " WHERE a.id = %s", (aid,))


def list_applications(c: Conn, job_id: int | None, student_id: int | None, status: str | None) -> list[dict]:
    where, params = ["TRUE"], []
    for col, val in (("a.job_id", job_id), ("a.student_id", student_id), ("a.status", status)):
        if val is not None:
            where.append(f"{col} = %s")
            params.append(val)
    return _all(c, APP_SELECT + f" WHERE {' AND '.join(where)} ORDER BY a.id", params)


def update_application_status(c: Conn, aid: int, status: str, expected_old: str) -> bool:
    """Compare-and-set: only changes the row if it still has the status we read (two reviewers cannot both win)."""
    cur = c.execute(
        "UPDATE applications SET status = %s, updated_at = now() WHERE id = %s AND status = %s",
        (status, aid, expected_old),
    )
    return cur.rowcount == 1


def insert_event(c: Conn, aid: int, old: str | None, new: str, actor: str) -> None:
    c.execute("INSERT INTO application_events (application_id, from_status, to_status, actor) VALUES (%s, %s, %s, %s)", (aid, old, new, actor))


def list_events(c: Conn, aid: int) -> list[dict]:
    return _all(c, "SELECT from_status, to_status, actor, at FROM application_events WHERE application_id = %s ORDER BY id", (aid,))


def count_by_status(c: Conn, jid: int) -> dict[str, int]:
    rows = _all(c, "SELECT status, COUNT(*) AS n FROM applications WHERE job_id = %s GROUP BY status", (jid,))
    return {r["status"]: r["n"] for r in rows}


# ------------------------------------------------------------------ interviews
def overlapping_interviews(c: Conn, starts: datetime, ends: datetime, student_id: int, panel: str, skip_application: int) -> list[dict]:
    """Interviews that overlap [starts, ends) for the same student or the same panel (other than this application's)."""
    return _all(
        c,
        "SELECT i.application_id, i.student_id, i.panel, i.starts_at, i.ends_at FROM interviews i "
        "WHERE i.application_id <> %s AND i.starts_at < %s AND i.ends_at > %s "
        "AND (i.student_id = %s OR lower(i.panel) = lower(%s))",
        (skip_application, ends, starts, student_id, panel),
    )


def upsert_interview(c: Conn, aid: int, sid: int, starts: datetime, ends: datetime, mode: str, location: str, panel: str, by: str) -> None:
    c.execute(
        "INSERT INTO interviews (application_id, student_id, starts_at, ends_at, mode, location, panel, created_by) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (application_id) DO UPDATE SET starts_at = EXCLUDED.starts_at, ends_at = EXCLUDED.ends_at, "
        "mode = EXCLUDED.mode, location = EXCLUDED.location, panel = EXCLUDED.panel, created_by = EXCLUDED.created_by",
        (aid, sid, starts, ends, mode, location, panel, by),
    )


def delete_interview(c: Conn, aid: int) -> bool:
    return c.execute("DELETE FROM interviews WHERE application_id = %s", (aid,)).rowcount > 0


INTERVIEW_SELECT = """
    SELECT i.id, i.application_id, i.student_id, i.starts_at, i.ends_at, i.mode, i.location, i.panel,
           s.name AS student_name, j.title AS job_title, c.name AS company_name
    FROM interviews i
    JOIN students s ON s.id = i.student_id
    JOIN applications a ON a.id = i.application_id
    JOIN jobs j ON j.id = a.job_id
    JOIN companies c ON c.id = j.company_id
"""


def get_interview(c: Conn, aid: int) -> dict | None:
    return _one(c, INTERVIEW_SELECT + " WHERE i.application_id = %s", (aid,))


def list_interviews(c: Conn, student_id: int | None, after: datetime | None) -> list[dict]:
    where, params = ["TRUE"], []
    if student_id is not None:
        where.append("i.student_id = %s")
        params.append(student_id)
    if after is not None:
        where.append("i.ends_at >= %s")
        params.append(after)
    return _all(c, INTERVIEW_SELECT + f" WHERE {' AND '.join(where)} ORDER BY i.starts_at", params)


# ------------------------------------------------------------------ notifications
def insert_notification(c: Conn, sid: int, aid: int | None, kind: str, message: str) -> None:
    c.execute("INSERT INTO notifications (student_id, application_id, kind, message) VALUES (%s, %s, %s, %s)", (sid, aid, kind, message))


def list_notifications(c: Conn, sid: int, limit: int = 50) -> list[dict]:
    return _all(
        c, "SELECT id, kind, message, application_id, created_at, read_at FROM notifications WHERE student_id = %s "
        "ORDER BY created_at DESC, id DESC LIMIT %s", (sid, limit),
    )


def unread_count(c: Conn, sid: int) -> int:
    return _one(c, "SELECT COUNT(*) AS n FROM notifications WHERE student_id = %s AND read_at IS NULL", (sid,))["n"]


def mark_read(c: Conn, sid: int, nid: int | None) -> int:
    """Marks one notification (nid) or all of them read. The student_id condition stops reading someone else's."""
    if nid is None:
        return c.execute("UPDATE notifications SET read_at = now() WHERE student_id = %s AND read_at IS NULL", (sid,)).rowcount
    # COALESCE keeps the first read time; marking an already-read notification is not an error
    return c.execute("UPDATE notifications SET read_at = COALESCE(read_at, now()) WHERE id = %s AND student_id = %s", (nid, sid)).rowcount


# ------------------------------------------------------------------ dashboard
def overview(c: Conn, now: datetime) -> dict:
    totals = _one(
        c,
        """SELECT
             (SELECT COUNT(*) FROM students) AS students,
             (SELECT COUNT(*) FROM students WHERE cgpa IS NULL) AS students_unverified,
             (SELECT COUNT(*) FROM jobs WHERE status = 'open') AS open_jobs,
             (SELECT COUNT(*) FROM applications) AS applications,
             (SELECT COUNT(*) FROM applications WHERE status = 'offered') AS offers,
             (SELECT COUNT(DISTINCT student_id) FROM applications WHERE status = 'offered') AS placed_students,
             (SELECT COUNT(*) FROM interviews WHERE starts_at >= %s) AS upcoming_interviews""",
        (now,),
    )
    funnel = {r["status"]: r["n"] for r in _all(c, "SELECT status, COUNT(*) AS n FROM applications GROUP BY status")}
    per_job = _all(
        c,
        """SELECT j.id AS job_id, j.title, c.name AS company_name, COUNT(a.id) AS applications,
                  COUNT(a.id) FILTER (WHERE a.status = 'offered') AS offers
           FROM jobs j JOIN companies c ON c.id = j.company_id LEFT JOIN applications a ON a.job_id = j.id
           GROUP BY j.id, c.name ORDER BY applications DESC, j.id LIMIT 10""",
    )
    branches = _all(
        c,
        """SELECT s.branch, COUNT(*) AS students,
                  COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM applications a WHERE a.student_id = s.id AND a.status = 'offered')) AS placed
           FROM students s GROUP BY s.branch ORDER BY s.branch""",
    )
    return {**totals, "status_funnel": funnel, "applications_per_job": per_job, "branch_placements": branches}


def applicants_for_export(c: Conn, jid: int) -> list[dict]:
    return _all(
        c,
        """SELECT a.id AS application_id, s.name, s.email, s.roll_no, s.branch, s.cgpa, s.skills, a.status,
                  a.created_at AS applied_at, i.starts_at AS interview_at, i.panel
           FROM applications a JOIN students s ON s.id = a.student_id LEFT JOIN interviews i ON i.application_id = a.id
           WHERE a.job_id = %s ORDER BY a.id""",
        (jid,),
    )
