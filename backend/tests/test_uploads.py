"""Resume uploads: type, size, storage location and access."""

from conftest import make_student, register

PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


def put(client, sid, content, name="cv.pdf", ctype="application/pdf", headers=None):
    return client.put(f"/students/{sid}/resume", files={"file": (name, content, ctype)}, headers=headers or {})


def test_upload_and_download_a_pdf(client):
    tok, h = register(client)
    sid = tok["me"]["student_id"]
    r = put(client, sid, PDF, headers=h)
    assert r.status_code == 200 and r.json()["resume_name"] == "cv.pdf"
    d = client.get(f"/students/{sid}/resume", headers=h)
    assert d.status_code == 200 and d.content == PDF and d.headers["content-type"] == "application/pdf"
    assert d.headers["x-content-type-options"] == "nosniff"


def test_non_pdf_large_or_empty_files_are_refused(client):
    s = make_student(client)
    assert put(client, s["id"], b"<html>not a pdf</html>", name="cv.pdf").status_code == 415  # the name says pdf, the bytes do not
    assert put(client, s["id"], PDF, ctype="text/html").status_code == 415
    assert put(client, s["id"], b"%PDF-" + b"0" * (2 * 1024 * 1024)).status_code == 413
    assert put(client, s["id"], b"").status_code == 422


def test_file_names_cannot_escape_the_upload_folder(client, tmp_path):
    s = make_student(client)
    r = put(client, s["id"], PDF, name="../../../etc/passwd.pdf")
    assert r.status_code == 200 and r.json()["resume_name"] == "passwd.pdf"
    files = list((tmp_path / "uploads").rglob("*.pdf"))
    assert len(files) == 1 and files[0].resolve().is_relative_to((tmp_path / "uploads").resolve())


def test_replacing_a_resume_deletes_the_old_file(client, tmp_path):
    s = make_student(client)
    put(client, s["id"], PDF, name="old.pdf")
    put(client, s["id"], PDF + b"%new", name="new.pdf")
    files = list((tmp_path / "uploads").rglob("*.pdf"))
    assert len(files) == 1 and files[0].read_bytes().endswith(b"%new")


def test_students_cannot_read_or_replace_each_others_resumes(client):
    a_tok, a = register(client, n=1)
    _, b = register(client, n=2)
    sid = a_tok["me"]["student_id"]
    put(client, sid, PDF, headers=a)
    assert client.get(f"/students/{sid}/resume", headers=b).status_code == 403
    assert put(client, sid, PDF, headers=b).status_code == 403
    assert client.get(f"/students/{sid}/resume").status_code == 200  # the officer can
