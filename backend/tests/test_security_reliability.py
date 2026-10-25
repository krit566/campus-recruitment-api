"""Auth and roles, idempotency keys, audit trail, request ids and metrics."""

from conftest import make_company, make_job, make_student, sql


def as_key(key):
    return {"X-API-Key": key}


def test_requests_without_or_with_wrong_key_are_401(client):
    assert client.get("/jobs", headers={"X-API-Key": ""}).status_code == 401
    assert client.get("/jobs", headers=as_key("nope")).status_code == 401


def test_student_key_is_returned_once_and_stored_hashed(client, db_url):
    s = make_student(client)
    assert s["api_key"].startswith("stu_")
    assert "api_key" not in client.get(f"/students/{s['id']}").json()
    stored = [r[0] for r in sql(db_url, "SELECT key_hash FROM api_keys")]
    assert s["api_key"] not in stored and len(stored[0]) == 64  # SHA-256 hex, never the key itself


def test_student_can_only_see_and_act_on_their_own_records(client):
    a = make_student(client, n=1)
    b = make_student(client, n=2)
    co = make_company(client)
    j = make_job(client, co["id"])
    ka = as_key(a["api_key"])
    assert client.get(f"/students/{a['id']}", headers=ka).status_code == 200
    assert client.get(f"/students/{b['id']}", headers=ka).status_code == 403
    assert client.get("/students", headers=ka).status_code == 403  # officer-only listing
    assert client.post("/applications", json={"student_id": b["id"], "job_id": j["id"]}, headers=ka).status_code == 403
    assert client.post("/applications", json={"student_id": a["id"], "job_id": j["id"]}, headers=ka).status_code == 201


def test_student_cannot_change_cgpa_or_promote_themselves(client):
    s = make_student(client)
    k = as_key(s["api_key"])
    assert client.patch(f"/students/{s['id']}", json={"cgpa": 10}, headers=k).status_code == 403
    assert client.patch(f"/students/{s['id']}", json={"skills": ["Go"]}, headers=k).status_code == 200
    co = make_company(client)
    j = make_job(client, co["id"])
    a = client.post("/applications", json={"student_id": s["id"], "job_id": j["id"]}, headers=k).json()
    assert client.patch(f"/applications/{a['id']}/status", json={"status": "shortlisted"}, headers=k).status_code == 403
    assert client.patch(f"/applications/{a['id']}/status", json={"status": "withdrawn"}, headers=k).status_code == 200


def test_students_only_list_their_own_applications(client):
    a, b = make_student(client, n=1), make_student(client, n=2)
    co = make_company(client)
    j = make_job(client, co["id"])
    for s in (a, b):
        client.post("/applications", json={"student_id": s["id"], "job_id": j["id"]})
    mine = client.get("/applications", headers=as_key(a["api_key"])).json()
    assert [x["student_id"] for x in mine] == [a["id"]]


def test_only_officer_creates_jobs_and_reads_metrics(client):
    s = make_student(client)
    co = make_company(client)
    k = as_key(s["api_key"])
    body = {"company_id": co["id"], "title": "SDE", "eligible_branches": ["CSE"], "openings": 1, "deadline": "2099-01-01"}
    assert client.post("/jobs", json=body, headers=k).status_code == 403
    assert client.get("/metrics", headers=k).status_code == 403


def test_idempotent_apply_runs_once_and_replays(client):
    s = make_student(client)
    co = make_company(client)
    j = make_job(client, co["id"])
    body = {"student_id": s["id"], "job_id": j["id"]}
    h = {"Idempotency-Key": "apply-123"}
    first = client.post("/applications", json=body, headers=h)
    retry = client.post("/applications", json=body, headers=h)
    assert first.status_code == retry.status_code == 201
    assert retry.json() == first.json() and retry.headers.get("Idempotent-Replayed") == "true"
    # without the key, the same request is a real second attempt and hits the duplicate rule
    assert client.post("/applications", json=body).status_code == 409


def test_same_idempotency_key_with_different_body_is_rejected(client):
    s1, s2 = make_student(client, n=1), make_student(client, n=2)
    co = make_company(client)
    j = make_job(client, co["id"])
    h = {"Idempotency-Key": "k-1"}
    client.post("/applications", json={"student_id": s1["id"], "job_id": j["id"]}, headers=h)
    r = client.post("/applications", json={"student_id": s2["id"], "job_id": j["id"]}, headers=h)
    assert r.status_code == 422 and "different request" in r.json()["detail"]


def test_failed_request_is_not_stored_so_a_fixed_retry_works(client):
    s = make_student(client, cgpa=6.0)
    co = make_company(client)
    j = make_job(client, co["id"], min_cgpa=7.0)
    h = {"Idempotency-Key": "k-2"}
    assert client.post("/applications", json={"student_id": s["id"], "job_id": j["id"]}, headers=h).status_code == 403
    client.patch(f"/students/{s['id']}", json={"cgpa": 8.0})
    assert client.post("/applications", json={"student_id": s["id"], "job_id": j["id"]}, headers=h).status_code == 201


def test_idempotent_status_change_is_applied_once(client):
    s = make_student(client)
    co = make_company(client)
    j = make_job(client, co["id"])
    a = client.post("/applications", json={"student_id": s["id"], "job_id": j["id"]}).json()
    h = {"Idempotency-Key": "move-1"}
    for _ in range(3):
        assert client.patch(f"/applications/{a['id']}/status", json={"status": "shortlisted"}, headers=h).status_code == 200
    assert [e["to_status"] for e in client.get(f"/applications/{a['id']}/history").json()] == ["applied", "shortlisted"]


def test_audit_trail_records_who_changed_what(client):
    s = make_student(client)
    co = make_company(client)
    j = make_job(client, co["id"])
    a = client.post("/applications", json={"student_id": s["id"], "job_id": j["id"]}, headers=as_key(s["api_key"])).json()
    client.patch(f"/applications/{a['id']}/status", json={"status": "shortlisted"})
    client.patch(f"/applications/{a['id']}/status", json={"status": "withdrawn"}, headers=as_key(s["api_key"]))
    ev = client.get(f"/applications/{a['id']}/history").json()
    assert [(e["from_status"], e["to_status"], e["actor"]) for e in ev] == [
        (None, "applied", f"student:{s['id']}"),
        ("applied", "shortlisted", "officer"),
        ("shortlisted", "withdrawn", f"student:{s['id']}"),
    ]


def test_request_id_is_echoed_or_generated(client):
    assert client.get("/health", headers={"X-Request-ID": "abc123"}).headers["X-Request-ID"] == "abc123"
    assert len(client.get("/health").headers["X-Request-ID"]) == 16


def test_metrics_group_by_route_template(client):
    s = make_student(client)
    client.get(f"/students/{s['id']}")
    client.get("/students/999")
    m = client.get("/metrics").json()["routes"]
    r = m["/students/{sid}"]
    assert r["requests"] == 2 and r["by_status"] == {"200": 1, "404": 1}
    assert "p95" in r["latency_ms"]
