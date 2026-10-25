"""Request and response models. Validation happens here, before any SQL runs."""

from __future__ import annotations

import re
from datetime import date
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


# ------------------------------------------------------------------ students
class StudentIn(BaseModel):
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
        if not EMAIL.match(v):
            raise ValueError("not a valid email address")
        return v.lower()

    @field_validator("skills")
    @classmethod
    def clean_skills(cls, v: list[str]) -> list[str]:
        out = []
        for s in v:
            s = s.strip()
            if not s or "," in s:
                raise ValueError("skills must be non-empty and must not contain commas")
            if s.lower() not in (x.lower() for x in out):
                out.append(s)
        return out


class StudentUpdate(BaseModel):
    """Partial update: only the fields that are sent change."""

    model_config = ConfigDict(str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=2, max_length=100)
    cgpa: float | None = Field(default=None, ge=0, le=10)
    skills: list[str] | None = None

    @field_validator("skills")
    @classmethod
    def clean_skills(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else StudentIn.clean_skills(v)


class Student(StudentIn):
    id: int


class StudentCreated(Student):
    api_key: str  # shown once; only its hash is stored


class Event(BaseModel):
    from_status: str | None
    to_status: str
    actor: str
    at: str


# ------------------------------------------------------------------ companies
class CompanyIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=100)
    website: str | None = Field(default=None, pattern=r"^https?://\S+$")


class Company(CompanyIn):
    id: int


# ------------------------------------------------------------------ jobs
class JobIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    company_id: int
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=5000)
    min_cgpa: float = Field(default=0, ge=0, le=10)
    eligible_branches: list[Branch] = Field(min_length=1)
    openings: int = Field(gt=0, le=1000)
    deadline: date


class Job(JobIn):
    id: int
    status: str


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
    created_at: str
    updated_at: str


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
