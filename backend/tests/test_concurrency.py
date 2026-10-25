"""Two reviewers send an offer for the LAST opening at the same moment: exactly one must win."""

from concurrent.futures import ThreadPoolExecutor

from conftest import make_company, make_job, make_student, sql


def test_parallel_offers_never_exceed_openings(client):
    co = make_company(client)
    j = make_job(client, co["id"], openings=1)
    apps = []
    for n in range(1, 9):
        s = make_student(client, n=n)
        a = client.post("/applications", json={"student_id": s["id"], "job_id": j["id"]}).json()
        client.patch(f"/applications/{a['id']}/status", json={"status": "shortlisted"})
        client.patch(f"/applications/{a['id']}/status", json={"status": "interview"})
        apps.append(a)

    def offer(a):
        return client.patch(f"/applications/{a['id']}/status", json={"status": "offered"}).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(offer, apps))

    assert codes.count(200) == 1, codes
    assert all(c == 409 for c in codes if c != 200), codes
    assert client.get(f"/jobs/{j['id']}/stats").json()["by_status"].get("offered") == 1


def test_simultaneous_first_attempts_with_one_idempotency_key_apply_once(client, db_url):
    """The gap the SQLite version documented: two FIRST attempts with the same key arriving together. The key is now
    reserved in the same transaction as the action, so the others wait and then replay the first response."""
    co = make_company(client)
    j = make_job(client, co["id"])
    s = make_student(client)
    body = {"student_id": s["id"], "job_id": j["id"]}

    def attempt(_):
        r = client.post("/applications", json=body, headers={"Idempotency-Key": "same-click"})
        return r.status_code, r.json()["id"], r.headers.get("Idempotent-Replayed")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))

    assert {code for code, _, _ in results} == {201}, results
    assert len({aid for _, aid, _ in results}) == 1  # everyone got the same application
    assert sum(1 for *_, replayed in results if replayed == "true") == 7
    assert sql(db_url, "SELECT COUNT(*) FROM applications")[0][0] == 1
    assert sql(db_url, "SELECT COUNT(*) FROM application_events")[0][0] == 1


def test_parallel_interview_bookings_for_one_panel_never_overlap(client, db_url):
    """Two officers book the same panel at the same time for different students: exactly one booking wins."""
    from datetime import datetime, timedelta, timezone

    co = make_company(client)
    j = make_job(client, co["id"], openings=8)
    apps = []
    for n in range(1, 7):
        st = make_student(client, n=n)
        a = client.post("/applications", json={"student_id": st["id"], "job_id": j["id"]}).json()
        client.patch(f"/applications/{a['id']}/status", json={"status": "shortlisted"})
        client.patch(f"/applications/{a['id']}/status", json={"status": "interview"})
        apps.append(a)
    start = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0).isoformat()

    def book(a):
        body = {"starts_at": start, "duration_minutes": 30, "panel": "Panel A"}
        return client.put(f"/applications/{a['id']}/interview", json=body).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = list(pool.map(book, apps))

    assert codes.count(200) == 1 and codes.count(409) == 5, codes
    assert sql(db_url, "SELECT COUNT(*) FROM interviews")[0][0] == 1
