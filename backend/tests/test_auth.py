"""Sign-up, login, tokens, lockout and roles for the web app."""

from datetime import datetime, timedelta, timezone

import jwt
from conftest import make_company, make_job, officer_login, register, sql

NO_KEY = {"X-API-Key": ""}
BASE = {"name": "New Student", "password": "long-enough-1", "branch": "IT", "graduation_year": 2028}


def test_register_signs_the_student_in(client):
    tok, h = register(client)
    assert tok["me"]["role"] == "student" and tok["me"]["name"] == "Reg Student 1"
    me = client.get("/auth/me", headers=h).json()
    assert me["email"] == "reg1@geu.ac.in" and me["student_id"] == tok["me"]["student_id"]


def test_register_needs_a_college_email_and_a_real_password(client):
    r = client.post("/auth/register", json={**BASE, "email": "x@gmail.com", "roll_no": "IT-900"}, headers=NO_KEY)
    assert r.status_code == 422 and "geu.ac.in" in r.json()["detail"]
    r = client.post("/auth/register", json={**BASE, "email": "x@geu.ac.in", "roll_no": "IT-900", "password": "short"}, headers=NO_KEY)
    assert r.status_code == 422


def test_duplicate_email_or_roll_number_is_409_and_leaves_nothing_behind(client, db_url):
    register(client, n=1)
    r = client.post("/auth/register", json={**BASE, "email": "reg1@geu.ac.in", "roll_no": "IT-777"}, headers=NO_KEY)
    assert r.status_code == 409 and "email" in r.json()["detail"]
    r = client.post("/auth/register", json={**BASE, "email": "new@geu.ac.in", "roll_no": "IT-001"}, headers=NO_KEY)
    assert r.status_code == 409 and "roll number" in r.json()["detail"]
    # the student row and the login are created in one transaction: a failed sign-up leaves no half-created student
    assert sql(db_url, "SELECT COUNT(*) FROM students")[0][0] == 1
    assert sql(db_url, "SELECT COUNT(*) FROM users")[0][0] == 1


def test_passwords_are_stored_as_bcrypt_hashes(client, db_url):
    register(client, password="correct-horse-1")
    (h,) = sql(db_url, "SELECT password_hash FROM users")[0]
    assert h.startswith("$2b$") and "correct-horse" not in h


def test_login_and_wrong_password(client):
    register(client, password="correct-horse-1")
    assert client.post("/auth/login", json={"email": "REG1@geu.ac.in", "password": "correct-horse-1"}, headers=NO_KEY).status_code == 200
    r = client.post("/auth/login", json={"email": "reg1@geu.ac.in", "password": "nope"}, headers=NO_KEY)
    assert r.status_code == 401 and r.json()["detail"] == "wrong email or password"
    # unknown emails get the same message, so the API does not reveal who has an account
    r = client.post("/auth/login", json={"email": "ghost@geu.ac.in", "password": "nope"}, headers=NO_KEY)
    assert r.json()["detail"] == "wrong email or password"


def test_five_wrong_passwords_lock_the_email(client):
    register(client, password="correct-horse-1")
    for _ in range(5):
        client.post("/auth/login", json={"email": "reg1@geu.ac.in", "password": "guess"}, headers=NO_KEY)
    r = client.post("/auth/login", json={"email": "reg1@geu.ac.in", "password": "correct-horse-1"}, headers=NO_KEY)
    assert r.status_code == 429


def test_expired_or_forged_tokens_are_rejected(client):
    tok, _ = register(client)
    sid = tok["me"]["student_id"]
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    expired = jwt.encode({"sub": "1", "role": "student", "sid": sid, "exp": past}, "test-jwt-secret-not-a-real-secret", algorithm="HS256")
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}", **NO_KEY})
    assert r.status_code == 401 and "expired" in r.json()["detail"]
    # a token that claims to be an officer but is signed with another secret
    forged = jwt.encode({"sub": "1", "role": "officer", "sid": None, "exp": past + timedelta(days=1)}, "attacker-secret", algorithm="HS256")
    assert client.get("/students", headers={"Authorization": f"Bearer {forged}", **NO_KEY}).status_code == 401


def test_student_token_cannot_use_officer_routes_or_change_cgpa(client):
    tok, h = register(client)
    sid = tok["me"]["student_id"]
    assert client.get("/students", headers=h).status_code == 403
    assert client.get("/stats/overview", headers=h).status_code == 403
    assert client.patch(f"/students/{sid}", json={"cgpa": 9.9}, headers=h).status_code == 403
    assert client.patch(f"/students/{sid}", json={"skills": ["React", "Go"]}, headers=h).json()["skills"] == ["React", "Go"]


def test_unverified_cgpa_blocks_applying_until_the_officer_sets_it(client):
    tok, h = register(client)
    sid = tok["me"]["student_id"]
    co = make_company(client)
    j = make_job(client, co["id"], min_cgpa=7)
    assert client.get(f"/students/{sid}/eligible-jobs", headers=h).json() == []
    r = client.post("/applications", json={"student_id": sid, "job_id": j["id"]}, headers=h)
    assert r.status_code == 403 and "verified" in r.json()["detail"]
    client.patch(f"/students/{sid}", json={"cgpa": 8.2})  # officer (API key)
    assert [x["id"] for x in client.get(f"/students/{sid}/eligible-jobs", headers=h).json()] == [j["id"]]
    assert client.post("/applications", json={"student_id": sid, "job_id": j["id"]}, headers=h).status_code == 201


def test_officer_login_is_recorded_in_the_audit_trail(client, db_url):
    oh = officer_login(client, db_url)
    tok, h = register(client)
    sid = tok["me"]["student_id"]
    client.patch(f"/students/{sid}", json={"cgpa": 8.0}, headers=oh)
    co = make_company(client)
    j = make_job(client, co["id"])
    a = client.post("/applications", json={"student_id": sid, "job_id": j["id"]}, headers=h).json()
    client.patch(f"/applications/{a['id']}/status", json={"status": "shortlisted"}, headers=oh)
    actors = [e["actor"] for e in client.get(f"/applications/{a['id']}/history", headers=oh).json()]
    officer_id = client.get("/auth/me", headers=oh).json()["user_id"]
    assert actors == [f"student:{sid}", f"officer:{officer_id}"]


def test_first_officer_is_created_from_environment_once(client, db_url, monkeypatch):
    from app import db
    from app.security import bootstrap_officer

    monkeypatch.setenv("RECRUIT_OFFICER_EMAIL", "Head@geu.ac.in")
    monkeypatch.setenv("RECRUIT_OFFICER_PASSWORD", "a-long-officer-password")
    with db.connection() as c:
        bootstrap_officer(c)
        bootstrap_officer(c)  # a second start does not create a duplicate
    assert sql(db_url, "SELECT email FROM users WHERE role = 'officer'") == [("head@geu.ac.in",)]
    r = client.post("/auth/login", json={"email": "head@geu.ac.in", "password": "a-long-officer-password"}, headers=NO_KEY)
    assert r.status_code == 200 and r.json()["me"]["role"] == "officer"
