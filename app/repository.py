"""Repository layer: the only place that writes SQL. Returns plain dicts; knows nothing about HTTP or business rules."""

from __future__ import annotations

import sqlite3


def _student(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    d["skills"] = [s for s in d["skills"].split(",") if s]
    d.pop("created_at", None)
    return d


def _job(r: sqlite3.Row | None) -> dict | None:
    if r is None:
        return None
    d = dict(r)
    d["eligible_branches"] = d["eligible_branches"].split(",")
    d.pop("created_at", None)
    return d


# ------------------------------------------------------------------ students
def insert_student(c: sqlite3.Connection, s: dict) -> int:
    cur = c.execute(
        "INSERT INTO students (name, email, roll_no, branch, cgpa, graduation_year, skills) VALUES (?,?,?,?,?,?,?)",
        (s["name"], s["email"], s["roll_no"], s["branch"], s["cgpa"], s["graduation_year"], ",".join(s["skills"])),
    )
    return cur.lastrowid


def get_student(c: sqlite3.Connection, sid: int) -> dict | None:
    return _student(c.execute("SELECT * FROM students WHERE id = ?", (sid,)).fetchone())


def list_students(c: sqlite3.Connection, branch: str | None, min_cgpa: float | None, skill: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
    where, params = ["1=1"], []
    if branch:
        where.append("branch = ?")
        params.append(branch)
    if min_cgpa is not None:
        where.append("cgpa >= ?")
        params.append(min_cgpa)
    if skill:
        # skills are stored as ',a,b,' style matching on word boundaries via instr on a padded string
        where.append("instr(',' || lower(skills) || ',', ',' || lower(?) || ',') > 0")
        params.append(skill)
    w = " AND ".join(where)
    total = c.execute(f"SELECT COUNT(*) FROM students WHERE {w}", params).fetchone()[0]
    rows = c.execute(f"SELECT * FROM students WHERE {w} ORDER BY id LIMIT ? OFFSET ?", [*params, limit, offset]).fetchall()
    return [_student(r) for r in rows], total


def update_student(c: sqlite3.Connection, sid: int, fields: dict) -> None:
    if "skills" in fields:
        fields = {**fields, "skills": ",".join(fields["skills"])}
    sets = ", ".join(f"{k} = ?" for k in fields)
    c.execute(f"UPDATE students SET {sets} WHERE id = ?", (*fields.values(), sid))


def delete_student(c: sqlite3.Connection, sid: int) -> bool:
    return c.execute("DELETE FROM students WHERE id = ?", (sid,)).rowcount > 0


# ------------------------------------------------------------------ companies
def insert_company(c: sqlite3.Connection, co: dict) -> int:
    return c.execute("INSERT INTO companies (name, website) VALUES (?, ?)", (co["name"], co.get("website"))).lastrowid


def get_company(c: sqlite3.Connection, cid: int) -> dict | None:
    r = c.execute("SELECT id, name, website FROM companies WHERE id = ?", (cid,)).fetchone()
    return dict(r) if r else None


def list_companies(c: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in c.execute("SELECT id, name, website FROM companies ORDER BY name").fetchall()]


# ------------------------------------------------------------------ jobs
def insert_job(c: sqlite3.Connection, j: dict) -> int:
    return c.execute(
        "INSERT INTO jobs (company_id, title, description, min_cgpa, eligible_branches, openings, deadline) VALUES (?,?,?,?,?,?,?)",
        (j["company_id"], j["title"], j["description"], j["min_cgpa"], ",".join(j["eligible_branches"]), j["openings"], j["deadline"]),
    ).lastrowid


def get_job(c: sqlite3.Connection, jid: int) -> dict | None:
    return _job(c.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone())


def list_jobs(c: sqlite3.Connection, status: str | None, company_id: int | None, branch: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
    where, params = ["1=1"], []
    if status:
        where.append("status = ?")
        params.append(status)
    if company_id:
        where.append("company_id = ?")
        params.append(company_id)
    if branch:
        where.append("instr(',' || eligible_branches || ',', ',' || ? || ',') > 0")
        params.append(branch)
    w = " AND ".join(where)
    total = c.execute(f"SELECT COUNT(*) FROM jobs WHERE {w}", params).fetchone()[0]
    rows = c.execute(f"SELECT * FROM jobs WHERE {w} ORDER BY deadline, id LIMIT ? OFFSET ?", [*params, limit, offset]).fetchall()
    return [_job(r) for r in rows], total


def eligible_jobs(c: sqlite3.Connection, branch: str, cgpa: float, today: str) -> list[dict]:
    rows = c.execute(
        "SELECT * FROM jobs WHERE status = 'open' AND deadline >= ? AND min_cgpa <= ? "
        "AND instr(',' || eligible_branches || ',', ',' || ? || ',') > 0 ORDER BY deadline, id",
        (today, cgpa, branch),
    ).fetchall()
    return [_job(r) for r in rows]


def set_job_status(c: sqlite3.Connection, jid: int, status: str) -> None:
    c.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, jid))


# ------------------------------------------------------------------ applications
def insert_application(c: sqlite3.Connection, sid: int, jid: int) -> int:
    return c.execute("INSERT INTO applications (student_id, job_id) VALUES (?, ?)", (sid, jid)).lastrowid


def get_application(c: sqlite3.Connection, aid: int) -> dict | None:
    r = c.execute("SELECT * FROM applications WHERE id = ?", (aid,)).fetchone()
    return dict(r) if r else None


def list_applications(c: sqlite3.Connection, job_id: int | None, student_id: int | None, status: str | None) -> list[dict]:
    where, params = ["1=1"], []
    for col, val in (("job_id", job_id), ("student_id", student_id), ("status", status)):
        if val is not None:
            where.append(f"{col} = ?")
            params.append(val)
    rows = c.execute(f"SELECT * FROM applications WHERE {' AND '.join(where)} ORDER BY id", params).fetchall()
    return [dict(r) for r in rows]


def update_application_status(c: sqlite3.Connection, aid: int, status: str, expected_old: str) -> bool:
    """Compare-and-set: only changes the row if it still has the status we read (two reviewers cannot both win)."""
    cur = c.execute(
        "UPDATE applications SET status = ?, updated_at = datetime('now') WHERE id = ? AND status = ?",
        (status, aid, expected_old),
    )
    return cur.rowcount == 1


def insert_event(c: sqlite3.Connection, aid: int, old: str | None, new: str, actor: str) -> None:
    c.execute("INSERT INTO application_events (application_id, from_status, to_status, actor) VALUES (?,?,?,?)", (aid, old, new, actor))


def list_events(c: sqlite3.Connection, aid: int) -> list[dict]:
    rows = c.execute("SELECT from_status, to_status, actor, at FROM application_events WHERE application_id = ? ORDER BY id", (aid,)).fetchall()
    return [dict(r) for r in rows]


def count_by_status(c: sqlite3.Connection, jid: int) -> dict[str, int]:
    rows = c.execute("SELECT status, COUNT(*) AS n FROM applications WHERE job_id = ? GROUP BY status", (jid,)).fetchall()
    return {r["status"]: r["n"] for r in rows}
