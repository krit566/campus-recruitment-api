from datetime import date, timedelta

from conftest import make_company, make_job, make_student


def test_job_needs_existing_company_and_future_deadline(client):
    assert client.post("/jobs", json={"company_id": 99, "title": "SDE", "eligible_branches": ["CSE"], "openings": 1, "deadline": "2099-01-01"}).status_code == 404
    co = make_company(client)
    past = (date.today() - timedelta(days=1)).isoformat()
    assert client.post("/jobs", json={"company_id": co["id"], "title": "SDE", "eligible_branches": ["CSE"], "openings": 1, "deadline": past}).status_code == 422


def test_job_validation(client):
    co = make_company(client)
    base = {"company_id": co["id"], "title": "SDE", "eligible_branches": ["CSE"], "openings": 1, "deadline": "2099-01-01"}
    assert client.post("/jobs", json={**base, "openings": 0}).status_code == 422
    assert client.post("/jobs", json={**base, "eligible_branches": []}).status_code == 422
    assert client.post("/jobs", json={**base, "min_cgpa": 11}).status_code == 422


def test_duplicate_company_name_is_409(client):
    make_company(client, "Visa")
    assert client.post("/companies", json={"name": "Visa"}).status_code == 409


def test_jobs_filter_by_branch_and_status(client):
    co = make_company(client)
    make_job(client, co["id"], eligible_branches=["CSE"])
    j2 = make_job(client, co["id"], eligible_branches=["ECE"])
    client.post(f"/jobs/{j2['id']}/close")
    assert client.get("/jobs?branch=CSE").json()["total"] == 1
    assert client.get("/jobs?status=closed").json()["total"] == 1


def test_eligible_jobs_for_a_student(client):
    co = make_company(client)
    make_job(client, co["id"], title="Open to CSE 7+", min_cgpa=7, eligible_branches=["CSE"])
    make_job(client, co["id"], title="Needs 9+", min_cgpa=9, eligible_branches=["CSE"])
    make_job(client, co["id"], title="ECE only", eligible_branches=["ECE"])
    s = make_student(client, cgpa=8.0, branch="CSE")
    titles = [j["title"] for j in client.get(f"/students/{s['id']}/eligible-jobs").json()]
    assert titles == ["Open to CSE 7+"]


def test_apply_happy_path(client):
    co = make_company(client)
    j = make_job(client, co["id"])
    s = make_student(client)
    r = client.post("/applications", json={"student_id": s["id"], "job_id": j["id"]})
    assert r.status_code == 201 and r.json()["status"] == "applied"


def test_cannot_apply_twice(client):
    co = make_company(client)
    j = make_job(client, co["id"])
    s = make_student(client)
    client.post("/applications", json={"student_id": s["id"], "job_id": j["id"]})
    r = client.post("/applications", json={"student_id": s["id"], "job_id": j["id"]})
    assert r.status_code == 409 and "already applied" in r.json()["detail"]


def test_eligibility_rules_are_enforced(client):
    co = make_company(client)
    j = make_job(client, co["id"], min_cgpa=8.5, eligible_branches=["CSE"])
    low = make_student(client, n=1, cgpa=8.0)
    wrong_branch = make_student(client, n=2, cgpa=9.5, branch="ME")
    r = client.post("/applications", json={"student_id": low["id"], "job_id": j["id"]})
    assert r.status_code == 403 and "CGPA" in r.json()["detail"]
    r = client.post("/applications", json={"student_id": wrong_branch["id"], "job_id": j["id"]})
    assert r.status_code == 403 and "branch" in r.json()["detail"]


def test_cannot_apply_to_closed_job_or_missing_records(client):
    co = make_company(client)
    j = make_job(client, co["id"])
    s = make_student(client)
    client.post(f"/jobs/{j['id']}/close")
    assert client.post("/applications", json={"student_id": s["id"], "job_id": j["id"]}).status_code == 409
    assert client.post("/applications", json={"student_id": 999, "job_id": j["id"]}).status_code == 404
    assert client.post("/applications", json={"student_id": s["id"], "job_id": 999}).status_code == 404


def _applied(client, openings=2, students=1):
    co = make_company(client)
    j = make_job(client, co["id"], openings=openings)
    apps = []
    for n in range(1, students + 1):
        s = make_student(client, n=n)
        apps.append(client.post("/applications", json={"student_id": s["id"], "job_id": j["id"]}).json())
    return j, apps


def _move(client, aid, status):
    return client.patch(f"/applications/{aid}/status", json={"status": status})


def test_full_workflow_to_offer(client):
    _, (a,) = _applied(client)
    for st in ("shortlisted", "interview", "offered"):
        r = _move(client, a["id"], st)
        assert r.status_code == 200 and r.json()["status"] == st


def test_invalid_transitions_are_409(client):
    _, (a,) = _applied(client)
    assert _move(client, a["id"], "offered").status_code == 409  # cannot skip shortlist + interview
    assert _move(client, a["id"], "rejected").status_code == 200
    assert _move(client, a["id"], "shortlisted").status_code == 409  # rejected is final


def test_withdraw_allowed_only_before_interview(client):
    _, (a, b) = _applied(client, students=2)
    assert _move(client, a["id"], "withdrawn").status_code == 200
    _move(client, b["id"], "shortlisted")
    _move(client, b["id"], "interview")
    assert _move(client, b["id"], "withdrawn").status_code == 409


def test_offers_cannot_exceed_openings_and_job_closes_when_full(client):
    j, apps = _applied(client, openings=1, students=2)
    for a in apps:
        _move(client, a["id"], "shortlisted")
        _move(client, a["id"], "interview")
    assert _move(client, apps[0]["id"], "offered").status_code == 200
    r = _move(client, apps[1]["id"], "offered")
    assert r.status_code == 409 and "openings" in r.json()["detail"]
    assert client.get(f"/jobs/{j['id']}").json()["status"] == "closed"


def test_unknown_status_is_422_and_missing_application_404(client):
    _, (a,) = _applied(client)
    assert _move(client, a["id"], "hired").status_code == 422
    assert _move(client, 999, "shortlisted").status_code == 404


def test_job_stats(client):
    j, apps = _applied(client, openings=3, students=3)
    _move(client, apps[0]["id"], "shortlisted")
    _move(client, apps[1]["id"], "rejected")
    st = client.get(f"/jobs/{j['id']}/stats").json()
    assert st["total_applications"] == 3
    assert st["by_status"] == {"applied": 1, "shortlisted": 1, "rejected": 1}
    assert st["offers_left"] == 3


def test_list_applications_filters(client):
    j, apps = _applied(client, students=2)
    _move(client, apps[0]["id"], "shortlisted")
    assert len(client.get(f"/applications?job_id={j['id']}").json()) == 2
    assert len(client.get("/applications?status=shortlisted").json()) == 1


def test_deleting_student_removes_their_applications(client):
    j, (a,) = _applied(client)
    client.delete(f"/students/{a['student_id']}")
    assert client.get(f"/applications?job_id={j['id']}").json() == []
