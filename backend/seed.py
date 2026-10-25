"""Fills an EMPTY database with fictional demo data, going through the same service functions as the API
(so every application has its audit trail, notifications and valid statuses).

    DATABASE_URL=postgresql://...  python seed.py            # refuses if students already exist
    DATABASE_URL=postgresql://...  python seed.py --reset    # wipes all data first (demo databases only!)

All people and companies are invented. Demo logins (change SEED_PASSWORD for anything public):
    officer@geu.ac.in            password: $SEED_PASSWORD (default "placeright-demo")
    <firstname>.<lastname>@geu.ac.in   same password, e.g. aarav.sharma@geu.ac.in
"""

from __future__ import annotations

import os
import random
import sys
from datetime import date, datetime, timedelta, timezone

from app import db
from app import repository as repo
from app import services as svc
from app.security import hash_password

FIRST = ["Aarav", "Diya", "Kabir", "Ananya", "Vihaan", "Isha", "Arjun", "Meera", "Reyansh", "Saanvi", "Ishaan", "Aditi",
         "Rohan", "Kavya", "Dev", "Nisha", "Aryan", "Pooja", "Kunal", "Riya", "Siddharth", "Tanvi", "Yash", "Neha",
         "Varun", "Sneha", "Harsh", "Anjali", "Manav", "Priya", "Nikhil", "Shreya", "Karan", "Simran", "Rahul", "Aisha",
         "Mohit", "Tara", "Aditya", "Bhavya"]
LAST = ["Sharma", "Verma", "Negi", "Rawat", "Bisht", "Joshi", "Gupta", "Singh", "Bhatt", "Thapa", "Kapoor", "Mehta",
        "Chauhan", "Pant", "Dobhal", "Saini", "Rana", "Kumar", "Nautiyal", "Arora"]
BRANCHES = ["CSE"] * 14 + ["IT"] * 9 + ["ECE"] * 7 + ["EE"] * 4 + ["ME"] * 4 + ["CE"] * 2
SKILLS = {
    "CSE": ["Python", "Java", "SQL", "React", "Docker", "DSA", "FastAPI", "Spring Boot", "AWS"],
    "IT": ["JavaScript", "React", "Node.js", "SQL", "Python", "Git", "TypeScript"],
    "ECE": ["Embedded C", "VLSI", "MATLAB", "Python", "IoT", "Signal Processing"],
    "EE": ["MATLAB", "Power Systems", "PLC", "Python", "AutoCAD"],
    "ME": ["SolidWorks", "AutoCAD", "ANSYS", "Python", "CAD"],
    "CE": ["AutoCAD", "STAAD Pro", "Revit", "Surveying"],
}

COMPANIES = [  # fictional companies
    ("Northwind Payments", "Fintech"),
    ("Bluepeak Systems", "Enterprise software"),
    ("Riverstone Analytics", "Data & AI"),
    ("Kestrel Mobility", "Automotive"),
    ("Lumen Grid Energy", "Energy"),
    ("Cedar Health Tech", "Healthtech"),
]
JOBS = [  # (company index, title, branches, min CGPA, openings, CTC LPA, location, days to deadline)
    (0, "Software Engineer Intern", ["CSE", "IT"], 7.5, 3, 12.0, "Bengaluru", 21),
    (0, "Payments QA Engineer", ["CSE", "IT", "ECE"], 7.0, 2, 8.5, "Bengaluru", 28),
    (1, "Backend Developer (Java)", ["CSE", "IT"], 7.0, 4, 10.0, "Pune", 18),
    (1, "Cloud Support Associate", ["CSE", "IT", "ECE", "EE"], 6.5, 5, 6.5, "Hyderabad", 35),
    (2, "Data Analyst", ["CSE", "IT", "ECE"], 7.0, 3, 9.0, "Gurugram", 25),
    (2, "Machine Learning Intern", ["CSE"], 8.0, 2, 14.0, "Remote", 14),
    (3, "Embedded Systems Engineer", ["ECE", "EE"], 7.0, 2, 8.0, "Chennai", 30),
    (3, "Design Engineer Trainee", ["ME"], 6.5, 3, 6.0, "Pune", 40),
    (4, "Electrical Design Engineer", ["EE", "ECE"], 6.5, 2, 7.0, "Dehradun", 33),
    (5, "Full-Stack Developer", ["CSE", "IT"], 7.5, 2, 11.0, "Noida", 20),
]
PANELS = ["Panel A (Tech)", "Panel B (Tech)", "Panel C (HR)"]


def main() -> None:
    random.seed(7)  # the same demo data every time
    url = db.database_url()
    db.migrate(url)
    db.open_pool(url)
    with db.connection() as c:
        if "--reset" in sys.argv:
            c.execute("TRUNCATE idempotency, api_keys, notifications, interviews, application_events, applications, "
                      "jobs, companies, users, students RESTART IDENTITY CASCADE")
        elif c.execute("SELECT COUNT(*) AS n FROM students").fetchone()["n"]:
            sys.exit("the database already has students; run with --reset to wipe it (demo databases only)")
        seed(c)
    db.close_pool()


def seed(c) -> None:
    pw_hash = hash_password(os.environ.get("SEED_PASSWORD", "placeright-demo"))  # one hash: every demo user shares it
    officer_id = repo.insert_user(c, "officer@geu.ac.in", pw_hash, "officer", None)
    officer = f"officer:{officer_id}"

    companies = [svc.create_company(c, {"name": n, "website": f"https://{n.split()[0].lower()}.example.com", "industry": ind})["id"]
                 for n, ind in COMPANIES]
    jobs = []
    for ci, title, branches, cg, openings, ctc, loc, days in JOBS:
        jobs.append(svc.create_job(c, {
            "company_id": companies[ci], "title": title, "location": loc, "ctc_lpa": ctc, "min_cgpa": cg,
            "eligible_branches": branches, "openings": openings, "deadline": date.today() + timedelta(days=days),
            "description": f"{title} at {COMPANIES[ci][0]} (fictional demo role). Work with a small team on real "
                           f"projects; mentoring and a final presentation. Location: {loc}.",
        }))

    students = []
    for i, branch in enumerate(BRANCHES):
        first, last = FIRST[i], LAST[i % len(LAST)]
        data = {
            "name": f"{first} {last}", "email": f"{first.lower()}.{last.lower()}@geu.ac.in",
            "roll_no": f"GE-{branch}-24{i + 1:03d}", "branch": branch, "graduation_year": 2028,
            "skills": random.sample(SKILLS[branch], k=min(3, len(SKILLS[branch]))),
        }
        sid = svc.register_student(c, data, pw_hash)
        if i % 13 != 5:  # three students are left unverified, as happens in a real term
            svc.update_student(c, sid, {"cgpa": round(random.uniform(6.2, 9.6), 2)})
        students.append(sid)

    apps = []
    for sid in students:
        eligible = svc.eligible_jobs(c, sid)
        for j in random.sample(eligible, k=min(len(eligible), random.choice([1, 2, 2, 3]))):
            apps.append(svc.apply(c, sid, j["id"], actor=f"student:{sid}"))

    # move applications through the workflow; offers stop automatically when a job's openings are filled
    start = datetime.now(timezone.utc).replace(hour=4, minute=0, second=0, microsecond=0) + timedelta(days=2)  # 09:30 IST
    slot = 0
    for a in apps:
        path = random.choices(
            [[], ["shortlisted"], ["rejected"], ["withdrawn"], ["shortlisted", "interview"],
             ["shortlisted", "interview", "offered"], ["shortlisted", "interview", "rejected"]],
            weights=[30, 18, 12, 4, 16, 12, 8],
        )[0]
        for status in path:
            try:
                actor = f"student:{a['student_id']}" if status == "withdrawn" else officer
                svc.change_status(c, a["id"], status, actor=actor, student_id=a["student_id"] if status == "withdrawn" else None)
            except svc.ApiError:
                break  # e.g. all openings already have offers
        if path == ["shortlisted", "interview"]:
            begins = start + timedelta(days=slot // 8, minutes=45 * (slot % 8))
            mode = random.choice(["online", "onsite"])
            where = f"https://meet.example.com/pr-{a['id']}" if mode == "online" else "Placement Cell, Room 2"
            try:
                svc.schedule_interview(c, a["id"], {"starts_at": begins, "duration_minutes": 30, "mode": mode,
                                                    "location": where, "panel": PANELS[slot % 3]}, actor=officer)
                slot += 1
            except svc.ApiError:
                pass
    spread_history(c)
    n = c.execute("SELECT COUNT(*) AS n FROM applications").fetchone()["n"]
    print(f"seeded {len(students)} students, {len(companies)} companies, {len(jobs)} jobs, {n} applications, {slot} interviews")


def spread_history(c) -> None:
    """The seed runs in a second, so every event would have the same time. Spread each application's history over
    the last three weeks (applied first, each later step 1-3 days after), as it would look mid-season."""
    now = datetime.now(timezone.utc)
    for row in c.execute("SELECT id FROM applications ORDER BY id").fetchall():
        aid = row["id"]
        t = now - timedelta(days=random.randint(12, 21), hours=random.randint(0, 9))
        events = c.execute("SELECT id FROM application_events WHERE application_id = %s ORDER BY id", (aid,)).fetchall()
        times = []
        for e in events:
            c.execute("UPDATE application_events SET at = %s WHERE id = %s", (t, e["id"]))
            times.append(t)
            t += timedelta(days=random.randint(1, 3), hours=random.randint(1, 6))
        c.execute("UPDATE applications SET created_at = %s, updated_at = %s WHERE id = %s", (times[0], times[-1], aid))
        # notifications follow the event they announce (status ones in order, the interview invite last)
        notes = c.execute("SELECT id FROM notifications WHERE application_id = %s ORDER BY id", (aid,)).fetchall()
        for i, n in enumerate(notes):
            when = times[min(i + 1, len(times) - 1)] + timedelta(minutes=5 * (i + 1))
            c.execute("UPDATE notifications SET created_at = %s WHERE id = %s", (when, n["id"]))


if __name__ == "__main__":
    main()
