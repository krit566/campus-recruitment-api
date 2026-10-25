"""Interview scheduling and clashes, student notifications, CSV export and the dashboard numbers."""

import csv
import io
from datetime import datetime, timedelta, timezone

from conftest import make_company, make_job, make_student, register

SOON = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=5, minute=0, second=0, microsecond=0)


def at(minutes):
    return (SOON + timedelta(minutes=minutes)).isoformat()


def to_interview(client, j, n=1, **student):
    s = make_student(client, n=n, **student)
    a = client.post("/applications", json={"student_id": s["id"], "job_id": j["id"]}).json()
    client.patch(f"/applications/{a['id']}/status", json={"status": "shortlisted"})
    client.patch(f"/applications/{a['id']}/status", json={"status": "interview"})
    return s, a


def book(client, aid, start, panel="Panel A", minutes=30, **headers):
    return client.put(f"/applications/{aid}/interview", json={"starts_at": start, "duration_minutes": minutes, "panel": panel}, headers=headers)


# ------------------------------------------------------------------ interviews
def test_schedule_only_in_the_interview_stage_and_in_the_future(client):
    co = make_company(client)
    j = make_job(client, co["id"], openings=5)
    s = make_student(client)
    a = client.post("/applications", json={"student_id": s["id"], "job_id": j["id"]}).json()
    assert book(client, a["id"], at(0)).status_code == 409  # still "applied"
    client.patch(f"/applications/{a['id']}/status", json={"status": "shortlisted"})
    client.patch(f"/applications/{a['id']}/status", json={"status": "interview"})
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert book(client, a["id"], past).status_code == 422
    assert book(client, a["id"], "2030-01-01T10:00:00").status_code == 422  # no time zone
    r = book(client, a["id"], at(0))
    assert r.status_code == 200 and r.json()["panel"] == "Panel A"


def test_student_and_panel_clashes_are_refused(client):
    co = make_company(client)
    j1 = make_job(client, co["id"], title="Backend Intern", openings=5)
    j2 = make_job(client, co["id"], title="Data Intern", openings=5)
    s, a1 = to_interview(client, j1, n=1)
    a2 = client.post("/applications", json={"student_id": s["id"], "job_id": j2["id"]}).json()
    client.patch(f"/applications/{a2['id']}/status", json={"status": "shortlisted"})
    client.patch(f"/applications/{a2['id']}/status", json={"status": "interview"})
    _, b = to_interview(client, j1, n=2)

    assert book(client, a1["id"], at(0), panel="Panel A").status_code == 200
    r = book(client, a2["id"], at(15), panel="Panel B")  # same student, overlapping time
    assert r.status_code == 409 and "student already has an interview" in r.json()["detail"]
    r = book(client, b["id"], at(10), panel="panel a")  # same panel (any letter case), overlapping time
    assert r.status_code == 409 and "Panel A" in r.json()["detail"]
    assert book(client, b["id"], at(30), panel="Panel A").status_code == 200  # back-to-back is fine
    assert book(client, a1["id"], at(-30), panel="Panel A").status_code == 200  # moving a slot never clashes with itself


def test_students_see_only_their_own_interviews(client):
    co = make_company(client)
    j = make_job(client, co["id"], openings=5)
    tok, h = register(client)
    sid = tok["me"]["student_id"]
    client.patch(f"/students/{sid}", json={"cgpa": 8.5})
    a = client.post("/applications", json={"student_id": sid, "job_id": j["id"]}, headers=h).json()
    client.patch(f"/applications/{a['id']}/status", json={"status": "shortlisted"})
    client.patch(f"/applications/{a['id']}/status", json={"status": "interview"})
    _, other = to_interview(client, j, n=5)
    book(client, a["id"], at(0))
    book(client, other["id"], at(60))
    mine = client.get("/interviews", headers=h).json()
    assert [i["application_id"] for i in mine] == [a["id"]]
    assert client.get(f"/applications/{other['id']}/interview", headers=h).status_code == 403
    assert len(client.get("/interviews").json()) == 2  # officer sees all
    assert book(client, a["id"], at(120), **h).status_code == 403  # students cannot book


def test_cancel_interview(client):
    co = make_company(client)
    j = make_job(client, co["id"])
    _, a = to_interview(client, j)
    book(client, a["id"], at(0))
    assert client.delete(f"/applications/{a['id']}/interview").status_code == 204
    assert client.get(f"/applications/{a['id']}/interview").status_code == 404
    assert client.delete(f"/applications/{a['id']}/interview").status_code == 404


# ------------------------------------------------------------------ notifications
def test_status_changes_and_interviews_notify_the_student(client):
    co = make_company(client, "Northwind Labs")
    j = make_job(client, co["id"], title="SDE Intern")
    tok, h = register(client)
    sid = tok["me"]["student_id"]
    client.patch(f"/students/{sid}", json={"cgpa": 8.5})
    a = client.post("/applications", json={"student_id": sid, "job_id": j["id"]}, headers=h).json()
    client.patch(f"/applications/{a['id']}/status", json={"status": "shortlisted"})
    client.patch(f"/applications/{a['id']}/status", json={"status": "interview"})
    book(client, a["id"], at(0))
    n = client.get("/notifications", headers=h).json()
    assert n["unread"] == 3
    kinds = [x["kind"] for x in n["items"]]
    assert kinds == ["interview", "status:interview", "status:shortlisted"]  # newest first
    assert "SDE Intern at Northwind Labs" in n["items"][-1]["message"]


def test_the_students_own_withdrawal_does_not_notify_them(client):
    co = make_company(client)
    j = make_job(client, co["id"])
    tok, h = register(client)
    sid = tok["me"]["student_id"]
    client.patch(f"/students/{sid}", json={"cgpa": 8.5})
    a = client.post("/applications", json={"student_id": sid, "job_id": j["id"]}, headers=h).json()
    client.patch(f"/applications/{a['id']}/status", json={"status": "withdrawn"}, headers=h)
    assert client.get("/notifications", headers=h).json()["unread"] == 0


def test_mark_read_one_or_all_and_only_your_own(client):
    co = make_company(client)
    j = make_job(client, co["id"])
    tok, h = register(client, n=1)
    _, other = register(client, n=2)
    sid = tok["me"]["student_id"]
    client.patch(f"/students/{sid}", json={"cgpa": 8.5})
    a = client.post("/applications", json={"student_id": sid, "job_id": j["id"]}, headers=h).json()
    client.patch(f"/applications/{a['id']}/status", json={"status": "shortlisted"})
    client.patch(f"/applications/{a['id']}/status", json={"status": "rejected"})
    items = client.get("/notifications", headers=h).json()["items"]
    assert client.post(f"/notifications/{items[0]['id']}/read", headers=other).status_code == 404
    assert client.post(f"/notifications/{items[0]['id']}/read", headers=h).status_code == 204
    assert client.post(f"/notifications/{items[0]['id']}/read", headers=h).status_code == 204  # repeat is fine
    assert client.get("/notifications", headers=h).json()["unread"] == 1
    assert client.post("/notifications/read-all", headers=h).json() == {"marked": 1}
    assert client.get("/notifications").status_code == 403  # officers have no notification inbox


# ------------------------------------------------------------------ export & dashboard
def test_csv_export_lists_applicants_and_defuses_formulas(client):
    co = make_company(client)
    j = make_job(client, co["id"])
    to_interview(client, j, n=1, name="=HYPERLINK(evil)")
    make_student(client, n=2)
    r = client.get(f"/jobs/{j['id']}/applicants.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 1 and rows[0]["status"] == "interview"
    assert rows[0]["name"] == "'=HYPERLINK(evil)"  # a spreadsheet shows it as text instead of running it
    assert rows[0]["skills"] == "Python, SQL"


def test_csv_export_is_officer_only(client):
    co = make_company(client)
    j = make_job(client, co["id"])
    _, h = register(client)
    assert client.get(f"/jobs/{j['id']}/applicants.csv", headers=h).status_code == 403


def test_overview_numbers(client):
    co = make_company(client)
    j = make_job(client, co["id"], openings=3)
    make_job(client, co["id"], title="Second role")
    _, a = to_interview(client, j, n=1)
    client.patch(f"/applications/{a['id']}/status", json={"status": "offered"})
    to_interview(client, j, n=2, branch="IT")
    make_student(client, n=3, branch="ECE")
    register(client, n=4)  # unverified CGPA
    o = client.get("/stats/overview").json()
    assert (o["students"], o["students_unverified"], o["open_jobs"], o["applications"], o["offers"]) == (4, 1, 2, 2, 1)
    assert o["placed_students"] == 1 and o["placement_rate"] == 0.25
    assert o["status_funnel"] == {"offered": 1, "interview": 1}
    assert {b["branch"]: (b["students"], b["placed"]) for b in o["branch_placements"]} == {"CSE": (1, 1), "IT": (2, 0), "ECE": (1, 0)}


def test_workflow_endpoint_matches_the_rules(client):
    w = client.get("/meta/workflow", headers={"X-API-Key": ""}).json()
    assert w["transitions"]["interview"] == ["offered", "rejected"] and "CSE" in w["branches"]
