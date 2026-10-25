import pytest
from conftest import make_student


def test_create_and_get_student(client):
    s = make_student(client)
    r = client.get(f"/students/{s['id']}")
    assert r.status_code == 200
    assert r.json()["email"] == "student1@geu.ac.in"
    assert r.json()["skills"] == ["Python", "SQL"]


def test_email_is_normalised_to_lowercase(client):
    s = make_student(client, email="Kriti.S@GEU.ac.in")
    assert s["email"] == "kriti.s@geu.ac.in"


@pytest.mark.parametrize(
    "field,value",
    [
        ("email", "not-an-email"),
        ("cgpa", 10.5),
        ("cgpa", -1),
        ("branch", "XYZ"),
        ("roll_no", "a b"),
        ("name", "A"),
        ("graduation_year", 1999),
        ("skills", ["Python", ""]),
        ("skills", ["a,b"]),
    ],
)
def test_invalid_student_is_rejected_with_422(client, field, value):
    body = {"name": "Valid Name", "email": "v@geu.ac.in", "roll_no": "CSE-100", "branch": "CSE", "cgpa": 8, "graduation_year": 2028}
    body[field] = value
    assert client.post("/students", json=body).status_code == 422


def test_duplicate_email_and_roll_no_give_409(client):
    make_student(client)
    r = client.post("/students", json={"name": "Other", "email": "student1@geu.ac.in", "roll_no": "CSE-999", "branch": "IT", "cgpa": 7, "graduation_year": 2028})
    assert r.status_code == 409 and "email" in r.json()["detail"]
    r = client.post("/students", json={"name": "Other", "email": "other@geu.ac.in", "roll_no": "CSE-001", "branch": "IT", "cgpa": 7, "graduation_year": 2028})
    assert r.status_code == 409 and "roll_no" in r.json()["detail"]


def test_duplicate_skills_are_merged(client):
    s = make_student(client, skills=["Python", "python", "SQL"])
    assert s["skills"] == ["Python", "SQL"]


def test_list_filters_and_pagination(client):
    make_student(client, n=1, branch="CSE", cgpa=9.1, skills=["Java"])
    make_student(client, n=2, branch="IT", cgpa=7.2, skills=["Python"])
    make_student(client, n=3, branch="CSE", cgpa=6.5, skills=["Python", "React"])
    assert client.get("/students?branch=CSE").json()["total"] == 2
    assert client.get("/students?min_cgpa=7").json()["total"] == 2
    assert client.get("/students?skill=python").json()["total"] == 2
    page = client.get("/students?limit=2&offset=2").json()
    assert page["total"] == 3 and len(page["items"]) == 1


def test_skill_filter_matches_whole_skills_only(client):
    make_student(client, n=1, skills=["JavaScript"])
    assert client.get("/students?skill=Java").json()["total"] == 0


def test_partial_update_changes_only_sent_fields(client):
    s = make_student(client)
    r = client.patch(f"/students/{s['id']}", json={"cgpa": 9.0})
    assert r.status_code == 200
    assert r.json()["cgpa"] == 9.0 and r.json()["name"] == s["name"]


def test_delete_student_then_404(client):
    s = make_student(client)
    assert client.delete(f"/students/{s['id']}").status_code == 204
    assert client.get(f"/students/{s['id']}").status_code == 404
    assert client.delete(f"/students/{s['id']}").status_code == 404
