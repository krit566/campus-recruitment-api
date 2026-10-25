import { useState, type FormEvent } from "react";
import { api, saveBlob, type Student } from "../../api";
import { useAuth } from "../../auth";
import { ErrorNote, fmtDate, Loading, useLoad } from "../../components/ui";

const MAX_BYTES = 2 * 1024 * 1024;

function ProfileForm({ student, onSaved }: { student: Student; onSaved: (s: Student) => void }) {
  const [name, setName] = useState(student.name);
  const [skills, setSkills] = useState(student.skills.join(", "));
  const [msg, setMsg] = useState("");
  const [error, setError] = useState<unknown>(null);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setMsg("");
    setError(null);
    try {
      const list = skills
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      onSaved(await api.updateStudent(student.id, { name, skills: list }));
      setMsg("Saved.");
    } catch (err) {
      setError(err);
    }
  };

  return (
    <form onSubmit={save} className="stack">
      <label>
        Full name
        <input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />
      </label>
      <label>
        Skills (comma separated)
        <input value={skills} onChange={(e) => setSkills(e.target.value)} />
      </label>
      <ErrorNote error={error} />
      <div className="row-actions">
        <button type="submit">Save changes</button>
        <span role="status" className="ok-text">
          {msg}
        </span>
      </div>
    </form>
  );
}

function ResumeBox({ student, onSaved }: { student: Student; onSaved: (s: Student) => void }) {
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const upload = async (file: File | undefined) => {
    setError(null);
    if (!file) return;
    // checked here for a quick message; the server checks again (size, and that the bytes really are a PDF)
    if (file.type && file.type !== "application/pdf") return setError(new Error("Please choose a PDF file."));
    if (file.size > MAX_BYTES) return setError(new Error("The resume must be at most 2 MB."));
    setBusy(true);
    try {
      onSaved(await api.uploadResume(student.id, file));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      {student.resume_name ? (
        <p>
          <span className="file-chip">📄 {student.resume_name}</span>{" "}
          <span className="muted">uploaded {student.resume_uploaded_at ? fmtDate(student.resume_uploaded_at) : ""}</span>{" "}
          <button type="button" className="link" onClick={async () => saveBlob(await api.resumeBlob(student.id), student.resume_name!)}>
            Download
          </button>
        </p>
      ) : (
        <p className="muted">No resume yet. Recruiters see it with every application.</p>
      )}
      <label className="file-drop">
        <span>{busy ? "Uploading…" : student.resume_name ? "Replace resume (PDF, max 2 MB)" : "Upload resume (PDF, max 2 MB)"}</span>
        <input type="file" accept="application/pdf,.pdf" disabled={busy} onChange={(e) => upload(e.target.files?.[0])} />
      </label>
      <ErrorNote error={error} />
    </div>
  );
}

export function Profile() {
  const { me } = useAuth();
  const sid = me!.student_id!;
  const [override, setOverride] = useState<Student | null>(null);
  const { data, error } = useLoad(() => api.student(sid), [sid]);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const student = override ?? data;

  return (
    <>
      <div className="page-head">
        <h1 tabIndex={-1}>Profile</h1>
        <p className="muted">{student.email}</p>
      </div>
      <div className="grid2">
        <section className="card" aria-labelledby="det-h">
          <h2 id="det-h">Your details</h2>
          <dl className="facts">
            <div>
              <dt>Roll number</dt>
              <dd>{student.roll_no}</dd>
            </div>
            <div>
              <dt>Branch</dt>
              <dd>{student.branch}</dd>
            </div>
            <div>
              <dt>CGPA</dt>
              <dd>{student.cgpa ?? <span className="pill warn">Not verified yet</span>}</dd>
            </div>
          </dl>
          <p className="hint">Roll number, branch and CGPA come from college records; ask the placement office to correct them.</p>
          <ProfileForm student={student} onSaved={setOverride} />
        </section>
        <section className="card" aria-labelledby="cv-h">
          <h2 id="cv-h">Resume</h2>
          <ResumeBox student={student} onSaved={setOverride} />
        </section>
      </div>
    </>
  );
}
