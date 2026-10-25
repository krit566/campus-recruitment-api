"""HTTP layer (FastAPI). Thin: authenticate, validate, call a service, shape the response.

    DATABASE_URL=postgresql://...  JWT_SECRET=...  uvicorn app.main:app --reload     # docs at /docs

Every route states who may call it: officer only, the student themself (or an officer), or any signed-in user.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, Header, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from psycopg import Connection

from . import db
from . import observability as obs
from . import repository as repo
from . import services as svc
from . import uploads
from .db import get_conn
from .idempotency import run_idempotent
from .schemas import (
    AppStatus,
    Application,
    ApplicationIn,
    Branch,
    Company,
    CompanyIn,
    Event,
    Interview,
    InterviewIn,
    Job,
    JobIn,
    JobStats,
    LoginIn,
    Me,
    Notification,
    Overview,
    Page,
    RegisterIn,
    StatusChange,
    Student,
    StudentCreated,
    StudentIn,
    StudentUpdate,
    TokenOut,
)
from .security import (
    Principal,
    authenticate,
    bootstrap_officer,
    check_secret,
    current_principal,
    hash_password,
    issue_token,
    require_officer,
    require_self_or_officer,
    require_student,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    check_secret()
    if os.environ.get("RUN_MIGRATIONS", "1") == "1":
        db.migrate()
    db.open_pool()
    with db.connection() as c:
        bootstrap_officer(c)
    yield
    db.close_pool()


app = FastAPI(title="PlaceRight: Campus Recruitment API", version="3.0.0", lifespan=lifespan)
app.middleware("http")(obs.middleware)
if os.environ.get("CORS_ORIGINS"):  # only needed when the web app is served from another origin
    app.add_middleware(
        CORSMiddleware, allow_origins=os.environ["CORS_ORIGINS"].split(","), allow_methods=["*"], allow_headers=["*"],
        expose_headers=["X-Request-ID", "Idempotent-Replayed"],
    )

Conn = Depends(get_conn)
Officer = Depends(require_officer)
StudentOnly = Depends(require_student)
Anyone = Depends(current_principal)
IdemKey = Header(default=None, alias="Idempotency-Key")


@app.exception_handler(svc.ApiError)
async def api_error(_: Request, e: svc.ApiError) -> JSONResponse:
    return JSONResponse({"detail": e.message}, status_code=e.status)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")  # browsers must not guess file types
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


# ------------------------------------------------------------------ meta
@app.get("/health", tags=["meta"])
def health(c: Connection = Conn) -> dict:
    c.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/metrics", tags=["meta"])
def metrics(_: Principal = Officer) -> dict:
    return obs.snapshot()


@app.get("/meta/workflow", tags=["meta"])
def workflow() -> dict:
    """The allowed status moves, so the web app shows only valid buttons (the API still enforces them)."""
    return {"transitions": {k: sorted(v) for k, v in svc.TRANSITIONS.items()}, "branches": [b.value for b in Branch]}


# ------------------------------------------------------------------ auth
def _college_domain() -> str:
    return os.environ.get("COLLEGE_EMAIL_DOMAIN", "geu.ac.in").lower()


def _token_response(c: Connection, user_id: int) -> dict:
    u = repo.get_user(c, user_id)
    token, ttl = issue_token(u)
    return {"access_token": token, "expires_in": ttl, "me": {"user_id": u["id"], "email": u["email"], "role": u["role"], "student_id": u["student_id"], "name": u["name"]}}


@app.post("/auth/register", response_model=TokenOut, status_code=201, tags=["auth"])
def register(body: RegisterIn, c: Connection = Conn):
    if not body.email.endswith("@" + _college_domain()):
        raise svc.ApiError(422, f"use your college email address (@{_college_domain()})")
    data = body.model_dump(mode="json", exclude={"password"})
    svc.register_student(c, data, hash_password(body.password))
    return _token_response(c, repo.get_user_by_email(c, body.email)["id"])  # signed in straight away


@app.post("/auth/login", response_model=TokenOut, tags=["auth"])
def login(body: LoginIn, c: Connection = Conn):
    user = authenticate(c, body.email, body.password)
    return _token_response(c, user["id"])


@app.get("/auth/me", response_model=Me, tags=["auth"])
def me(p: Principal = Anyone, c: Connection = Conn):
    if p.user_id:
        u = repo.get_user(c, p.user_id)
        if not u:
            raise svc.ApiError(401, "this account no longer exists")
        return {"user_id": u["id"], "email": u["email"], "role": u["role"], "student_id": u["student_id"], "name": u["name"]}
    s = repo.get_student(c, p.student_id) if p.student_id else None
    return {"user_id": None, "email": s["email"] if s else None, "role": p.role, "student_id": p.student_id, "name": s["name"] if s else None}


# ------------------------------------------------------------------ students
@app.post("/students", response_model=StudentCreated, status_code=201, tags=["students"])
def create_student(body: StudentIn, c: Connection = Conn, _: Principal = Officer):
    return svc.create_student(c, body.model_dump(mode="json"))


@app.get("/students", response_model=Page, tags=["students"])
def list_students(
    branch: Branch | None = None,
    min_cgpa: float | None = Query(default=None, ge=0, le=10),
    skill: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    unverified: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    c: Connection = Conn,
    _: Principal = Officer,
):
    items, total = repo.list_students(c, branch.value if branch else None, min_cgpa, skill, q, unverified, limit, offset)
    return {"items": [Student(**s).model_dump(mode="json") for s in items], "total": total, "limit": limit, "offset": offset}


@app.get("/students/{sid}", response_model=Student, tags=["students"])
def get_student(sid: int, c: Connection = Conn, p: Principal = Anyone):
    require_self_or_officer(p, sid)
    return svc.get_student(c, sid)


@app.patch("/students/{sid}", response_model=Student, tags=["students"])
def update_student(sid: int, body: StudentUpdate, c: Connection = Conn, p: Principal = Anyone):
    require_self_or_officer(p, sid)
    fields = body.model_dump(exclude_none=True)
    if p.role == "student" and "cgpa" in fields:
        raise svc.ApiError(403, "CGPA is updated by the placement office from official results")
    return svc.update_student(c, sid, fields)


@app.delete("/students/{sid}", status_code=204, tags=["students"])
def delete_student(sid: int, c: Connection = Conn, _: Principal = Officer):
    path = (repo.get_resume(c, sid) or {}).get("resume_path")
    svc.delete_student(c, sid)
    uploads.remove_quietly(path)


@app.get("/students/{sid}/eligible-jobs", response_model=list[Job], tags=["students"])
def eligible_jobs(sid: int, c: Connection = Conn, p: Principal = Anyone):
    require_self_or_officer(p, sid)
    return svc.eligible_jobs(c, sid)


@app.put("/students/{sid}/resume", response_model=Student, tags=["students"])
async def upload_resume(sid: int, file: UploadFile = File(...), c: Connection = Conn, p: Principal = Anyone):
    require_self_or_officer(p, sid)
    svc.get_student(c, sid)
    old = (repo.get_resume(c, sid) or {}).get("resume_path")
    path, name = await uploads.save_resume(sid, file)
    repo.set_resume(c, sid, path, name)
    uploads.remove_quietly(old)  # the previous file is deleted only after the new one is recorded
    return svc.get_student(c, sid)


@app.get("/students/{sid}/resume", tags=["students"])
def download_resume(sid: int, c: Connection = Conn, p: Principal = Anyone):
    require_self_or_officer(p, sid)
    r = repo.get_resume(c, sid)
    if not r or not os.path.exists(r["resume_path"]):
        raise svc.ApiError(404, "no resume uploaded")
    return FileResponse(r["resume_path"], media_type="application/pdf", filename=r["resume_name"])


# ------------------------------------------------------------------ companies
@app.post("/companies", response_model=Company, status_code=201, tags=["companies"])
def create_company(body: CompanyIn, c: Connection = Conn, _: Principal = Officer):
    return svc.create_company(c, body.model_dump())


@app.get("/companies", response_model=list[Company], tags=["companies"])
def list_companies(c: Connection = Conn, _: Principal = Anyone):
    return repo.list_companies(c)


# ------------------------------------------------------------------ jobs
@app.post("/jobs", response_model=Job, status_code=201, tags=["jobs"])
def create_job(body: JobIn, c: Connection = Conn, _: Principal = Officer):
    return svc.create_job(c, body.model_dump())


@app.get("/jobs", response_model=Page, tags=["jobs"])
def list_jobs(
    status: str | None = Query(default=None, pattern="^(open|closed)$"),
    company_id: int | None = None,
    branch: Branch | None = None,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    c: Connection = Conn,
    _: Principal = Anyone,
):
    items, total = repo.list_jobs(c, status, company_id, branch.value if branch else None, q, limit, offset)
    return {"items": [Job(**j).model_dump(mode="json") for j in items], "total": total, "limit": limit, "offset": offset}


@app.get("/jobs/{jid}", response_model=Job, tags=["jobs"])
def get_job(jid: int, c: Connection = Conn, _: Principal = Anyone):
    return svc.get_job(c, jid)


@app.post("/jobs/{jid}/close", response_model=Job, tags=["jobs"])
def close_job(jid: int, c: Connection = Conn, _: Principal = Officer):
    return svc.close_job(c, jid)


@app.get("/jobs/{jid}/stats", response_model=JobStats, tags=["jobs"])
def job_stats(jid: int, c: Connection = Conn, _: Principal = Officer):
    return svc.job_stats(c, jid)


@app.get("/jobs/{jid}/applicants.csv", tags=["jobs"])
def export_applicants(jid: int, c: Connection = Conn, _: Principal = Officer):
    return Response(
        svc.applicants_csv(c, jid), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="job-{jid}-applicants.csv"'},
    )


# ------------------------------------------------------------------ applications
@app.post("/applications", response_model=Application, status_code=201, tags=["applications"])
def apply(body: ApplicationIn, request: Request, c: Connection = Conn, p: Principal = Anyone, idem: str | None = IdemKey):
    require_self_or_officer(p, body.student_id)
    return run_idempotent(c, request, p.name, idem, body.model_dump(), 201, lambda: svc.apply(c, body.student_id, body.job_id, actor=p.name))


@app.get("/applications", response_model=list[Application], tags=["applications"])
def list_applications(
    job_id: int | None = None,
    student_id: int | None = None,
    status: AppStatus | None = None,
    c: Connection = Conn,
    p: Principal = Anyone,
):
    if p.role == "student":
        student_id = p.student_id  # students only ever see their own applications
    return repo.list_applications(c, job_id, student_id, status.value if status else None)


def _own_application(c: Connection, p: Principal, aid: int) -> dict:
    a = svc.get_application(c, aid)
    if p.role == "student" and a["student_id"] != p.student_id:
        raise svc.ApiError(403, "students can only access their own records")
    return a


@app.get("/applications/{aid}", response_model=Application, tags=["applications"])
def get_application(aid: int, c: Connection = Conn, p: Principal = Anyone):
    return _own_application(c, p, aid)


@app.patch("/applications/{aid}/status", response_model=Application, tags=["applications"])
def change_status(aid: int, body: StatusChange, request: Request, c: Connection = Conn, p: Principal = Anyone, idem: str | None = IdemKey):
    as_student = p.student_id if p.role == "student" else None
    return run_idempotent(
        c, request, p.name, idem, {"aid": aid, **body.model_dump(mode="json")}, 200,
        lambda: svc.change_status(c, aid, body.status.value, actor=p.name, student_id=as_student),
    )


@app.get("/applications/{aid}/history", response_model=list[Event], tags=["applications"])
def application_history(aid: int, c: Connection = Conn, p: Principal = Anyone):
    a = repo.get_application(c, aid)
    if a and p.role == "student" and a["student_id"] != p.student_id:
        raise svc.ApiError(403, "students can only access their own records")
    return svc.history(c, aid)


# ------------------------------------------------------------------ interviews
@app.put("/applications/{aid}/interview", response_model=Interview, tags=["interviews"])
def schedule_interview(aid: int, body: InterviewIn, c: Connection = Conn, p: Principal = Officer):
    return svc.schedule_interview(c, aid, body.model_dump(), actor=p.name)


@app.get("/applications/{aid}/interview", response_model=Interview, tags=["interviews"])
def get_interview(aid: int, c: Connection = Conn, p: Principal = Anyone):
    _own_application(c, p, aid)
    i = repo.get_interview(c, aid)
    if not i:
        raise svc.ApiError(404, "no interview is scheduled for this application")
    return i


@app.delete("/applications/{aid}/interview", status_code=204, tags=["interviews"])
def cancel_interview(aid: int, c: Connection = Conn, _: Principal = Officer):
    svc.cancel_interview(c, aid)


@app.get("/interviews", response_model=list[Interview], tags=["interviews"])
def list_interviews(upcoming: bool = True, c: Connection = Conn, p: Principal = Anyone):
    after = datetime.now(timezone.utc) if upcoming else None
    return repo.list_interviews(c, p.student_id if p.role == "student" else None, after)


# ------------------------------------------------------------------ notifications (students)
@app.get("/notifications", tags=["notifications"])
def notifications(c: Connection = Conn, p: Principal = StudentOnly) -> dict:
    items = [Notification(**n).model_dump(mode="json") for n in repo.list_notifications(c, p.student_id)]
    return {"items": items, "unread": repo.unread_count(c, p.student_id)}


@app.post("/notifications/{nid}/read", status_code=204, tags=["notifications"])
def read_notification(nid: int, c: Connection = Conn, p: Principal = StudentOnly):
    if not repo.mark_read(c, p.student_id, nid):
        raise svc.ApiError(404, "notification not found")


@app.post("/notifications/read-all", tags=["notifications"])
def read_all(c: Connection = Conn, p: Principal = StudentOnly) -> dict:
    return {"marked": repo.mark_read(c, p.student_id, None)}


# ------------------------------------------------------------------ dashboard (officer)
@app.get("/stats/overview", response_model=Overview, tags=["dashboard"])
def overview(c: Connection = Conn, _: Principal = Officer):
    return svc.overview(c)
