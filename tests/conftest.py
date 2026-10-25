import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FUTURE = (date.today() + timedelta(days=30)).isoformat()
OFFICER_KEY = "test-officer-key-not-a-real-secret"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A fresh SQLite file per test, so tests never depend on each other. Requests run as the placement officer
    unless a test passes another X-API-Key."""
    monkeypatch.setenv("RECRUIT_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("RECRUIT_ADMIN_KEY", OFFICER_KEY)
    from app import observability
    from app.main import app

    observability.reset()
    with TestClient(app, headers={"X-API-Key": OFFICER_KEY}) as c:
        yield c


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
