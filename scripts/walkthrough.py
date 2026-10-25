"""End-to-end walkthrough against a running server: retries, eligibility, ownership, workflow and the offer race.

    $env:RECRUIT_ADMIN_KEY = "<key>"; uvicorn app.main:app      (use an empty database: RECRUIT_DB=walk.db)
    python scripts/walkthrough.py [http://127.0.0.1:8000]
"""

import json
import os
import sys
from datetime import date, timedelta
import concurrent.futures as cf

import httpx

B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
O = {"X-API-Key": os.environ["RECRUIT_ADMIN_KEY"]}

def show(label, r, keep=None):
    body = r.json() if r.content else None
    if isinstance(body, dict) and keep: body = {k: body[k] for k in keep if k in body}
    extra = "  Idempotent-Replayed: true" if r.headers.get("idempotent-replayed") else ""
    print(f"{label}\n  -> {r.status_code}{extra}  {json.dumps(body)}")
c = httpx.Client(base_url=B, timeout=10)
co = c.post("/companies", headers=O, json={"name": "Visa", "website": "https://visa.com"}); show("POST /companies (officer)", co)
job = c.post("/jobs", headers=O, json={"company_id": co.json()["id"], "title": "SWE Intern", "min_cgpa": 7.5, "eligible_branches": ["CSE", "IT"], "openings": 1, "deadline": str(date.today() + timedelta(days=60))})
show("POST /jobs  openings=1, min CGPA 7.5, CSE/IT", job, ["id", "title", "openings", "status"]); jid = job.json()["id"]
studs = []
for i, (n, br, g) in enumerate([("Asha", "CSE", 8.4), ("Ravi", "IT", 8.0), ("Meera", "ME", 9.1), ("Kabir", "CSE", 6.9)]):
    r = c.post("/students", headers=O, json={"name": n, "email": f"{n.lower()}@geu.ac.in", "roll_no": f"GE-24-{i:03d}", "branch": br, "cgpa": g, "graduation_year": 2028})
    studs.append(r.json())
print("POST /students x4  -> 201, each returns its own API key once (only a SHA-256 hash is stored)")
S = lambda s: {"X-API-Key": s["api_key"]}
r1 = c.post("/applications", headers={**S(studs[0]), "Idempotency-Key": "a1"}, json={"student_id": studs[0]["id"], "job_id": jid})
show("Asha (student) applies, Idempotency-Key: a1", r1, ["id", "status"]); a1 = r1.json()["id"]
show("same request retried after a timeout (key a1)", c.post("/applications", headers={**S(studs[0]), "Idempotency-Key": "a1"}, json={"student_id": studs[0]["id"], "job_id": jid}), ["id", "status"])
show("Meera (ME branch) applies", c.post("/applications", headers=S(studs[2]), json={"student_id": studs[2]["id"], "job_id": jid}))
show("Kabir (CGPA 6.9) applies", c.post("/applications", headers=S(studs[3]), json={"student_id": studs[3]["id"], "job_id": jid}))
show("Ravi tries to apply as Asha", c.post("/applications", headers=S(studs[1]), json={"student_id": studs[0]["id"], "job_id": jid}))
a2 = c.post("/applications", headers=S(studs[1]), json={"student_id": studs[1]["id"], "job_id": jid}).json()
show("Officer: applied -> offered (skips interview)", c.patch(f"/applications/{a1}/status", headers=O, json={"status": "offered"}))
for aid in (a1, a2["id"]):
    for st in ("shortlisted", "interview"): c.patch(f"/applications/{aid}/status", headers=O, json={"status": st})
with cf.ThreadPoolExecutor(8) as ex:
    rs = list(ex.map(lambda aid: httpx.patch(f"{B}/applications/{aid}/status", headers=O, json={"status": "offered"}, timeout=10).status_code, [a1, a2["id"]]))
print(f"Two reviewers offer the last opening at the same moment\n  -> {sorted(rs)}  (exactly one 200, the other 409)")
show(f"GET /jobs/{jid}/stats", c.get(f"/jobs/{jid}/stats", headers=O))
show(f"GET /jobs/{jid}", c.get(f"/jobs/{jid}", headers=O), ["status"])
h = c.get(f"/applications/{a1}/history", headers=O).json()
print(f"GET /applications/{a1}/history (Asha)\n  -> " + " | ".join(f"{e['from_status']}->{e['to_status']} by {e['actor']}" for e in h))
