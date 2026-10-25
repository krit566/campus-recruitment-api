"""Tests run against a REAL Postgres, because the race-safety rules (row locks, unique constraints, the idempotency
reservation) are database behaviour that a fake would not reproduce.

- CI sets DATABASE_URL to a Postgres service container.
- Locally, if DATABASE_URL is not set, a throwaway Postgres is started with `pgserver` (pip install pgserver).

The schema is migrated once per test run; every test starts from empty tables.
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FUTURE = (date.today() + timedelta(days=30)).isoformat()
OFFICER_KEY = "test-officer-key-not-a-real-secret"
TABLES = "idempotency, api_keys, notifications, interviews, application_events, applications, jobs, companies, users, students"


@pytest.fixture(scope="session")
def database_url(tmp_path_factory):
    url = os.environ.get("DATABASE_URL")
    server = None
    if not url:
        import pgserver

        server = pgserver.get_server(str(tmp_path_factory.mktemp("pgdata")), cleanup_mode="stop")
        url = server.get_uri()
    from app.db import migrate

    migrate(url)
    yield url
    if server is not None:
        server.cleanup()


@pytest.fixture
def db_url(database_url):
    with psycopg.connect(database_url, autocommit=True) as c:
        c.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
    return database_url


@pytest.fixture
def client(db_url, tmp_path, monkeypatch):
    """Requests run as the placement officer (API key) unless a test passes other headers."""
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("RUN_MIGRATIONS", "0")
    monkeypatch.setenv("RECRUIT_ADMIN_KEY", OFFICER_KEY)
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-not-a-real-secret")
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")  # fast hashing in tests only
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    from app import observability, security
    from app.main import app

    observability.reset()
    security.reset_lockouts()
    with TestClient(app, headers={"X-API-Key": OFFICER_KEY}) as c:
        yield c


def sql(db_url, query, params=()):
    with psycopg.connect(db_url, autocommit=True) as c:
        cur = c.execute(query, params)
        return cur.fetchall() if cur.description else []  # INSERT/UPDATE return no rows


def make_student(client, **over):
    n = over.pop("n", 1)
    body = {
        "name": f"Student {n}",
        "email": f"student{n}@geu.ac.in",
        "roll_no": f"CSE-{n:03d}",
        "branch": "CSE",
        "cgpa": 8.0,
        "graduation_year": 2028,
        "skills": ["Python", "SQL"],
        **over,
    }
    r = client.post("/students", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def make_company(client, name="Acme Payments"):
    r = client.post("/companies", json={"name": name, "website": "https://acme.example.com"})
    assert r.status_code == 201, r.text
    return r.json()


def make_job(client, company_id, **over):
    body = {
        "company_id": company_id,
        "title": "Software Engineering Intern",
        "min_cgpa": 7.0,
        "eligible_branches": ["CSE", "IT"],
        "openings": 2,
        "deadline": FUTURE,
        **over,
    }
    r = client.post("/jobs", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def register(client, n=1, password="correct-horse-1", **over):
    """Self-registration through the web flow; returns (token response, auth headers)."""
    body = {
        "name": f"Reg Student {n}",
        "email": f"reg{n}@geu.ac.in",
        "password": password,
        "roll_no": f"IT-{n:03d}",
        "branch": "IT",
        "graduation_year": 2028,
        "skills": ["React"],
        **over,
    }
    r = client.post("/auth/register", json=body, headers={"X-API-Key": ""})
    assert r.status_code == 201, r.text
    return r.json(), {"Authorization": f"Bearer {r.json()['access_token']}", "X-API-Key": ""}


def officer_login(client, db_url, email="officer@geu.ac.in", password="officer-password-123"):
    from app.security import hash_password

    sql(db_url, "INSERT INTO users (email, password_hash, role) VALUES (%s, %s, 'officer') ON CONFLICT DO NOTHING", (email, hash_password(password)))
    r = client.post("/auth/login", json={"email": email, "password": password}, headers={"X-API-Key": ""})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}", "X-API-Key": ""}
