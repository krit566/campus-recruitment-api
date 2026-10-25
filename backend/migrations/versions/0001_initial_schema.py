"""Initial schema: students, users, companies, jobs, applications, audit events, interviews, notifications,
API keys and idempotency records.

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = """
CREATE TABLE students (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                TEXT NOT NULL,
    email               TEXT NOT NULL UNIQUE,            -- stored lower-case
    roll_no             TEXT NOT NULL UNIQUE,
    branch              TEXT NOT NULL CHECK (branch IN ('CSE', 'IT', 'ECE', 'EE', 'ME', 'CE')),
    cgpa                DOUBLE PRECISION CHECK (cgpa >= 0 AND cgpa <= 10),  -- NULL until the placement office verifies it
    graduation_year     INTEGER NOT NULL,
    skills              TEXT[] NOT NULL DEFAULT '{}',
    resume_path         TEXT,                            -- file on the uploads volume; never the client's file name
    resume_name         TEXT,                            -- original name, only shown to people
    resume_uploaded_at  TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- people who sign in with email + password (officers, and students who registered themselves)
CREATE TABLE users (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email          TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,                        -- bcrypt, never the password
    role           TEXT NOT NULL CHECK (role IN ('officer', 'student')),
    student_id     BIGINT UNIQUE REFERENCES students(id) ON DELETE CASCADE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at  TIMESTAMPTZ,
    CHECK ((role = 'student') = (student_id IS NOT NULL))
);

CREATE TABLE companies (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    website     TEXT,
    industry    TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE jobs (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id         BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    title              TEXT NOT NULL,
    description        TEXT NOT NULL DEFAULT '',
    location           TEXT NOT NULL DEFAULT '',
    ctc_lpa            DOUBLE PRECISION CHECK (ctc_lpa > 0),   -- annual pay in lakh rupees, optional
    min_cgpa           DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (min_cgpa >= 0 AND min_cgpa <= 10),
    eligible_branches  TEXT[] NOT NULL CHECK (cardinality(eligible_branches) > 0),
    openings           INTEGER NOT NULL CHECK (openings > 0),
    deadline           DATE NOT NULL,
    status             TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE applications (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id  BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    job_id      BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'applied'
                CHECK (status IN ('applied', 'shortlisted', 'interview', 'offered', 'rejected', 'withdrawn')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT one_application_per_job UNIQUE (student_id, job_id)
);

-- audit trail: every application status change, who made it and when
CREATE TABLE application_events (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id  BIGINT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    from_status     TEXT,
    to_status       TEXT NOT NULL,
    actor           TEXT NOT NULL,
    at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- one interview slot per application; clashes are checked in services.schedule_interview under locks
CREATE TABLE interviews (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id  BIGINT NOT NULL UNIQUE REFERENCES applications(id) ON DELETE CASCADE,
    student_id      BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    starts_at       TIMESTAMPTZ NOT NULL,
    ends_at         TIMESTAMPTZ NOT NULL,
    mode            TEXT NOT NULL CHECK (mode IN ('online', 'onsite')),
    location        TEXT NOT NULL DEFAULT '',
    panel           TEXT NOT NULL,                       -- interviewer or panel name
    created_by      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (ends_at > starts_at)
);

-- messages shown to a student: status changes and interview invitations
CREATE TABLE notifications (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id      BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    application_id  BIGINT REFERENCES applications(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,
    message         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at         TIMESTAMPTZ
);

-- API keys for programmatic access: only the SHA-256 of a key is stored
CREATE TABLE api_keys (
    key_hash    TEXT PRIMARY KEY,
    role        TEXT NOT NULL CHECK (role IN ('officer', 'student')),
    student_id  BIGINT REFERENCES students(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- idempotency: the key is reserved in the SAME transaction as the action, then the response is stored with it
CREATE TABLE idempotency (
    principal    TEXT NOT NULL,
    key          TEXT NOT NULL,
    method       TEXT NOT NULL,
    path         TEXT NOT NULL,
    body_hash    TEXT NOT NULL,
    status_code  INTEGER,
    response     JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (principal, key)
);

CREATE INDEX ix_jobs_company ON jobs (company_id);
CREATE INDEX ix_apps_job_status ON applications (job_id, status);
CREATE INDEX ix_apps_student ON applications (student_id);
CREATE INDEX ix_events_app ON application_events (application_id);
CREATE INDEX ix_interviews_student ON interviews (student_id, starts_at);
CREATE INDEX ix_interviews_panel ON interviews (panel, starts_at);
CREATE INDEX ix_notifications_student ON notifications (student_id, created_at DESC);
"""


def upgrade() -> None:
    op.execute(SCHEMA)


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS idempotency, api_keys, notifications, interviews, application_events, "
        "applications, jobs, companies, users, students CASCADE"
    )
