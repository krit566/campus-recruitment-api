"""HTTP layer (FastAPI). Thin: authenticate, validate, call a service, shape the response.

    $env:RECRUIT_ADMIN_KEY = "<a long random string>"     # the placement officer's key
    uvicorn app.main:app --reload                          # API docs at http://127.0.0.1:8000/docs

Every route states who may call it: officer only, the student themself (or an officer), or any signed-in user.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse

from . import observability as obs
from . import repository as repo
from . import services as svc
from .db import get_conn, init_db
from .idempotency import run_idempotent
from .schemas import (
    AppStatus,
    Application,
    ApplicationIn,
    Branch,
    Company,
    CompanyIn,
    Event,
    Job,
    JobIn,
    JobStats,
    Page,
    StatusChange,
    Student,
    StudentCreated,
    StudentIn,
    StudentUpdate,
)
from .security import Principal, current_principal, require_officer, require_self_or_officer


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    init_db()
    yield


app = FastAPI(title="Campus Recruitment Management API", version="2.0.0", lifespan=lifespan)
app.middleware("http")(obs.middleware)
Conn = Depends(get_conn)
Officer = Depends(require_officer)
Anyone = Depends(current_principal)
IdemKey = Header(default=None, alias="Idempotency-Key")


@app.exception_handler(svc.ApiError)
async def api_error(_: Request, e: svc.ApiError) -> JSONResponse:
    return JSONResponse({"detail": e.message}, status_code=e.status)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}


@app.get("/metrics", tags=["meta"])
def metrics(_: Principal = Officer) -> dict:
    return obs.snapshot()


# ------------------------------------------------------------------ students
@app.post("/students", response_model=StudentCreated, status_code=201, tags=["students"])
def create_student(body: StudentIn, c: sqlite3.Connection = Conn, _: Principal = Officer):
    return svc.create_student(c, body.model_dump(mode="json"))


@app.get("/students", response_model=Page, tags=["students"])
def list_students(
    branch: Branch | None = None,
    min_cgpa: float | None = Query(default=None, ge=0, le=10),
    skill: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    c: sqlite3.Connection = Conn,
    _: Principal = Officer,
):
    items, total = repo.list_students(c, branch.value if branch else None, min_cgpa, skill, limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/students/{sid}", response_model=Student, tags=["students"])
def get_student(sid: int, c: sqlite3.Connection = Conn, p: Principal = Anyone):
    require_self_or_officer(p, sid)
    return svc.get_student(c, sid)


@app.patch("/students/{sid}", response_model=Student, tags=["students"])
def update_student(sid: int, body: StudentUpdate, c: sqlite3.Connection = Conn, p: Principal = Anyone):
    require_self_or_officer(p, sid)
    fields = body.model_dump(exclude_none=True)
    if p.role == "student" and "cgpa" in fields:
        raise svc.ApiError(403, "CGPA is updated by the placement office from official results")
    return svc.update_student(c, sid, fields)


@app.delete("/students/{sid}", status_code=204, tags=["students"])
def delete_student(sid: int, c: sqlite3.Connection = Conn, _: Principal = Officer):
    svc.delete_student(c, sid)


@app.get("/students/{sid}/eligible-jobs", response_model=list[Job], tags=["students"])
def eligible_jobs(sid: int, c: sqlite3.Connection = Conn, p: Principal = Anyone):
    require_self_or_officer(p, sid)
    return svc.eligible_jobs(c, sid)


# ------------------------------------------------------------------ companies
@app.post("/companies", response_model=Company, status_code=201, tags=["companies"])
def create_company(body: CompanyIn, c: sqlite3.Connection = Conn, _: Principal = Officer):
    return svc.create_company(c, body.model_dump())


@app.get("/companies", response_model=list[Company], tags=["companies"])
def list_companies(c: sqlite3.Connection = Conn, _: Principal = Anyone):
    return repo.list_companies(c)


# ------------------------------------------------------------------ jobs
@app.post("/jobs", response_model=Job, status_code=201, tags=["jobs"])
def create_job(body: JobIn, c: sqlite3.Connection = Conn, _: Principal = Officer):
    return svc.create_job(c, body.model_dump(mode="json"))


@app.get("/jobs", response_model=Page, tags=["jobs"])
def list_jobs(
    status: str | None = Query(default=None, pattern="^(open|closed)$"),
    company_id: int | None = None,
    branch: Branch | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    c: sqlite3.Connection = Conn,
    _: Principal = Anyone,
):
    items, total = repo.list_jobs(c, status, company_id, branch.value if branch else None, limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@app.get("/jobs/{jid}", response_model=Job, tags=["jobs"])
def get_job(jid: int, c: sqlite3.Connection = Conn, _: Principal = Anyone):
    return svc.get_job(c, jid)


@app.post("/jobs/{jid}/close", response_model=Job, tags=["jobs"])
def close_job(jid: int, c: sqlite3.Connection = Conn, _: Principal = Officer):
    return svc.close_job(c, jid)


@app.get("/jobs/{jid}/stats", response_model=JobStats, tags=["jobs"])
def job_stats(jid: int, c: sqlite3.Connection = Conn, _: Principal = Officer):
    return svc.job_stats(c, jid)


# ------------------------------------------------------------------ applications
@app.post("/applications", response_model=Application, status_code=201, tags=["applications"])
def apply(body: ApplicationIn, request: Request, c: sqlite3.Connection = Conn, p: Principal = Anyone, idem: str | None = IdemKey):
    require_self_or_officer(p, body.student_id)
    return run_idempotent(c, request, p.name, idem, body.model_dump(), 201, lambda: svc.apply(c, body.student_id, body.job_id, actor=p.name))


@app.get("/applications", response_model=list[Application], tags=["applications"])
def list_applications(
    job_id: int | None = None,
    student_id: int | None = None,
    status: AppStatus | None = None,
    c: sqlite3.Connection = Conn,
    p: Principal = Anyone,
):
    if p.role == "student":
        student_id = p.student_id  # students only ever see their own applications
    return repo.list_applications(c, job_id, student_id, status.value if status else None)


@app.patch("/applications/{aid}/status", response_model=Application, tags=["applications"])
def change_status(aid: int, body: StatusChange, request: Request, c: sqlite3.Connection = Conn, p: Principal = Anyone, idem: str | None = IdemKey):
    as_student = p.student_id if p.role == "student" else None
    return run_idempotent(
        c, request, p.name, idem, {"aid": aid, **body.model_dump(mode="json")}, 200,
        lambda: svc.change_status(c, aid, body.status.value, actor=p.name, student_id=as_student),
    )


@app.get("/applications/{aid}/history", response_model=list[Event], tags=["applications"])
def application_history(aid: int, c: sqlite3.Connection = Conn, p: Principal = Anyone):
    a = repo.get_application(c, aid)
    if a and p.role == "student" and a["student_id"] != p.student_id:
        raise svc.ApiError(403, "students can only access their own records")
    return svc.history(c, aid)
