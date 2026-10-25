"""End-to-end walkthrough against a running API with an EMPTY database: sign-up, CGPA verification, retries,
eligibility, ownership, the workflow, the race for the last opening, interview clashes and notifications.

    # API running with RECRUIT_ADMIN_KEY set and a fresh database
    $env:RECRUIT_ADMIN_KEY = "<key>"; python scripts/walkthrough.py [http://127.0.0.1:8000]
"""

import concurrent.futures as cf
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import httpx

B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OFFICER = {"X-API-Key": os.environ["RECRUIT_ADMIN_KEY"]}


def show(label, r, keep=None):
    body = r.json() if r.content else None
    if isinstance(body, dict) and keep:
        body = {k: body[k] for k in keep if k in body}
    extra = "  Idempotent-Replayed: true" if r.headers.get("idempotent-replayed") else ""
    print(f"{label}\n  -> {r.status_code}{extra}  {json.dumps(body)}")


c = httpx.Client(base_url=B, timeout=10)
co = c.post("/companies", headers=OFFICER, json={"name": "Northwind Payments", "industry": "Fintech"})
show("POST /companies (officer)", co, ["id", "name"])
job = c.post("/jobs", headers=OFFICER, json={
    "company_id": co.json()["id"], "title": "SWE Intern", "min_cgpa": 7.5, "eligible_branches": ["CSE", "IT"],
    "openings": 1, "deadline": str(date.today() + timedelta(days=60)),
})
show("POST /jobs  openings=1, min CGPA 7.5, CSE/IT", job, ["id", "title", "openings", "status"])
jid = job.json()["id"]

r = c.post("/auth/register", json={"name": "Mallory", "email": "mallory@gmail.com", "password": "long-password-1",
                                   "roll_no": "X-1", "branch": "CSE", "graduation_year": 2028})
show("Sign-up with a non-college email", r)

people = {}
for name, branch, cgpa in [("Asha", "CSE", 8.4), ("Ravi", "IT", 8.0), ("Meera", "ME", 9.1), ("Kabir", "CSE", 6.9)]:
    t = c.post("/auth/register", json={"name": f"{name} Demo", "email": f"{name.lower()}@geu.ac.in", "password": "long-password-1",
                                       "roll_no": f"GE-{branch}-{len(people) + 1:03d}", "branch": branch, "graduation_year": 2028}).json()
    people[name] = {"id": t["me"]["student_id"], "h": {"Authorization": f"Bearer {t['access_token']}"}, "cgpa": cgpa}
print("POST /auth/register x4  -> 201, each student is signed in (password stored as a bcrypt hash)")

asha = people["Asha"]
show("Asha applies before her CGPA is verified", c.post("/applications", headers=asha["h"], json={"student_id": asha["id"], "job_id": jid}))
for p in people.values():
    c.patch(f"/students/{p['id']}", headers=OFFICER, json={"cgpa": p["cgpa"]})
print("PATCH /students/{id} {cgpa} x4 (officer enters official CGPAs)")

idem = {**asha["h"], "Idempotency-Key": "a1"}
r1 = c.post("/applications", headers=idem, json={"student_id": asha["id"], "job_id": jid})
show("Asha applies, Idempotency-Key: a1", r1, ["id", "status"])
a1 = r1.json()["id"]
show("same request retried after a timeout (key a1)", c.post("/applications", headers=idem, json={"student_id": asha["id"], "job_id": jid}), ["id", "status"])
show("Meera (ME branch) applies", c.post("/applications", headers=people["Meera"]["h"], json={"student_id": people["Meera"]["id"], "job_id": jid}))
show("Kabir (CGPA 6.9) applies", c.post("/applications", headers=people["Kabir"]["h"], json={"student_id": people["Kabir"]["id"], "job_id": jid}))
ravi = people["Ravi"]
show("Ravi tries to apply as Asha", c.post("/applications", headers=ravi["h"], json={"student_id": asha["id"], "job_id": jid}))
show("Ravi tries to set his own CGPA", c.patch(f"/students/{ravi['id']}", headers=ravi["h"], json={"cgpa": 10}))
a2 = c.post("/applications", headers=ravi["h"], json={"student_id": ravi["id"], "job_id": jid}).json()["id"]

show("Officer: applied -> offered (skips the interview)", c.patch(f"/applications/{a1}/status", headers=OFFICER, json={"status": "offered"}))
for aid in (a1, a2):
    for st in ("shortlisted", "interview"):
        c.patch(f"/applications/{aid}/status", headers=OFFICER, json={"status": st})

slot = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=5, minute=0, second=0, microsecond=0)
show("Interview for Asha, Panel A, 30 min", c.put(f"/applications/{a1}/interview", headers=OFFICER,
                                                  json={"starts_at": slot.isoformat(), "panel": "Panel A"}), ["starts_at", "panel"])
show("Interview for Ravi, same panel, 15 min later", c.put(f"/applications/{a2}/interview", headers=OFFICER,
                                                           json={"starts_at": (slot + timedelta(minutes=15)).isoformat(), "panel": "Panel A"}))

with cf.ThreadPoolExecutor(8) as ex:
    rs = list(ex.map(lambda aid: httpx.patch(f"{B}/applications/{aid}/status", headers=OFFICER, json={"status": "offered"}, timeout=10).status_code, [a1, a2]))
print(f"Two reviewers offer the last opening at the same moment\n  -> {sorted(rs)}  (exactly one 200, the other 409)")
show(f"GET /jobs/{jid}/stats", c.get(f"/jobs/{jid}/stats", headers=OFFICER), ["by_status", "offers_left"])
show(f"GET /jobs/{jid}", c.get(f"/jobs/{jid}", headers=OFFICER), ["status"])
notes = c.get("/notifications", headers=asha["h"]).json()
print(f"GET /notifications (Asha)\n  -> {notes['unread']} unread, newest: \"{notes['items'][0]['message']}\"")
