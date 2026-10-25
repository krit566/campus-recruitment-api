"""Two reviewers send an offer for the LAST opening at the same moment: exactly one must win."""

from concurrent.futures import ThreadPoolExecutor

from conftest import make_company, make_job, make_student


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
