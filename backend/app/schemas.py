"""Request and response models. Validation happens here, before any SQL runs."""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


class Branch(str, Enum):
    CSE = "CSE"
    IT = "IT"
    ECE = "ECE"
    EE = "EE"
    ME = "ME"
    CE = "CE"


class AppStatus(str, Enum):
    applied = "applied"
    shortlisted = "shortlisted"
    interview = "interview"
    offered = "offered"
    rejected = "rejected"
    withdrawn = "withdrawn"


def _email(v: str) -> str:
    if not EMAIL.match(v):
        raise ValueError("not a valid email address")
    return v.lower()


def _skills(v: list[str]) -> list[str]:
    out: list[str] = []
    for s in v:
        s = s.strip()
        if not s or "," in s:
            raise ValueError("skills must be non-empty and must not contain commas")
        if s.lower() not in (x.lower() for x in out):
            out.append(s)
    return out


# ------------------------------------------------------------------ auth
class RegisterIn(BaseModel):
    """A student signs up themself. CGPA is not accepted here: the placement office enters it from official results."""

    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=72)  # bcrypt only uses the first 72 bytes
    roll_no: str = Field(min_length=3, max_length=20, pattern=r"^[A-Za-z0-9-]+$")
    branch: Branch
    graduation_year: int = Field(ge=2020, le=2035)
    skills: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        return _email(v)

    @field_validator("skills")
    @classmethod
    def clean_skills(cls, v: list[str]) -> list[str]:
        return _skills(v)

    @field_validator("password")
    @classmethod
    def password_bytes(cls, v: str) -> str:
        if len(v.encode()) > 72:
            raise ValueError("password is too long (max 72 bytes)")
        return v


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class Me(BaseModel):
    user_id: int | None
    email: str | None
    role: str
    student_id: int | None
    name: str | None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    me: Me


# ------------------------------------------------------------------ students
class StudentIn(BaseModel):
    """Created by the placement officer (bulk import, students without a login); returns an API key once."""

    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(max_length=254)
    roll_no: str = Field(min_length=3, max_length=20, pattern=r"^[A-Za-z0-9-]+$")
    branch: Branch
    cgpa: float = Field(ge=0, le=10)
    graduation_year: int = Field(ge=2020, le=2035)
    skills: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        return _email(v)

    @field_validator("skills")
    @classmethod
    def clean_skills(cls, v: list[str]) -> list[str]:
        return _skills(v)


class StudentUpdate(BaseModel):
    """Partial update: only the fields that are sent change."""

    model_config = ConfigDict(str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=2, max_length=100)
    cgpa: float | None = Field(default=None, ge=0, le=10)
    skills: list[str] | None = Field(default=None, max_length=30)

    @field_validator("skills")
    @classmethod
    def clean_skills(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _skills(v)


class Student(BaseModel):
    id: int
    name: str
    email: str
    roll_no: str
    branch: Branch
    cgpa: float | None  # None = not verified yet
    graduation_year: int
    skills: list[str]
    resume_name: str | None = None
    resume_uploaded_at: datetime | None = None


class StudentCreated(Student):
    api_key: str  # shown once; only its hash is stored


class Event(BaseModel):
    from_status: str | None
    to_status: str
    actor: str
    at: datetime


# ------------------------------------------------------------------ companies
class CompanyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=100)
    website: str | None = Field(default=None, pattern=r"^https?://\S+$")
    industry: str = Field(default="", max_length=60)


class Company(CompanyIn):
    id: int
    open_jobs: int = 0


# ------------------------------------------------------------------ jobs
class JobIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    company_id: int
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=5000)
    location: str = Field(default="", max_length=80)
    ctc_lpa: float | None = Field(default=None, gt=0, le=200)
    min_cgpa: float = Field(default=0, ge=0, le=10)
    eligible_branches: list[Branch] = Field(min_length=1)
    openings: int = Field(gt=0, le=1000)
    deadline: date


class Job(JobIn):
    id: int
    status: str
    company_name: str | None = None
    applications: int | None = None


# ------------------------------------------------------------------ interviews
class InterviewIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    starts_at: datetime
    duration_minutes: int = Field(default=30, ge=15, le=240)
    mode: str = Field(default="online", pattern="^(online|onsite)$")
    location: str = Field(default="", max_length=200)  # meeting link or room
    panel: str = Field(min_length=2, max_length=100)

    @field_validator("starts_at")
    @classmethod
    def needs_timezone(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("starts_at must include a time zone, e.g. 2026-11-03T10:00:00+05:30")
        return v


class Interview(BaseModel):
    id: int
    application_id: int
    student_id: int
    starts_at: datetime
    ends_at: datetime
    mode: str
    location: str
    panel: str
    student_name: str | None = None
    job_title: str | None = None
    company_name: str | None = None


# ------------------------------------------------------------------ applications
class ApplicationIn(BaseModel):
    student_id: int
    job_id: int


class StatusChange(BaseModel):
    status: AppStatus


class Application(BaseModel):
    id: int
    student_id: int
    job_id: int
    status: AppStatus
    created_at: datetime
    updated_at: datetime
    # joined details for the screens (present on list endpoints)
    student_name: str | None = None
    student_email: str | None = None
    roll_no: str | None = None
    branch: str | None = None
    cgpa: float | None = None
    job_title: str | None = None
    company_name: str | None = None
    interview_at: datetime | None = None


class JobStats(BaseModel):
    job_id: int
    openings: int
    total_applications: int
    by_status: dict[str, int]
    offers_left: int


class Page(BaseModel):
    items: list
    total: int
    limit: int
    offset: int


# ------------------------------------------------------------------ notifications & dashboard
class Notification(BaseModel):
    id: int
    kind: str
    message: str
    application_id: int | None
    created_at: datetime
    read_at: datetime | None


class Overview(BaseModel):
    students: int
    students_unverified: int
    open_jobs: int
    applications: int
    offers: int
    placed_students: int
    placement_rate: float  # placed students / students, 0..1
    status_funnel: dict[str, int]
    applications_per_job: list[dict]
    branch_placements: list[dict]
    upcoming_interviews: int
