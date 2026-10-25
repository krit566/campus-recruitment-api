import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type Student } from "../../api";
import { EmptyState, ErrorNote, Loading, useLoad } from "../../components/ui";

const PAGE = 20;

/** Inline CGPA entry: the placement office types the official value; students cannot change it themselves. */
function CgpaCell({ student, onSaved }: { student: Student; onSaved: () => void }) {
  const [editing, setEditing] = useState(student.cgpa === null);
  const [value, setValue] = useState(student.cgpa?.toString() ?? "");
  const [error, setError] = useState<unknown>(null);
  if (!editing)
    return (
      <>
        {student.cgpa}{" "}
        <button type="button" className="link small" onClick={() => setEditing(true)} aria-label={`Edit CGPA of ${student.name}`}>
          Edit
        </button>
      </>
    );
  return (
    <form
      className="inline-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        try {
          await api.updateStudent(student.id, { cgpa: Number(value) });
          setEditing(false);
          onSaved();
        } catch (err) {
          setError(err);
        }
      }}
    >
      <label className="sr-only" htmlFor={`cg-${student.id}`}>
        CGPA of {student.name}
      </label>
      <input id={`cg-${student.id}`} type="number" step="0.01" min="0" max="10" required value={value} onChange={(e) => setValue(e.target.value)} />
      <button type="submit" className="mini">
        Save
      </button>
      <ErrorNote error={error} />
    </form>
  );
}

export function Students() {
  const [params, setParams] = useSearchParams();
  const unverified = params.get("unverified") === "1";
  const [q, setQ] = useState("");
  const [branch, setBranch] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, error, reload } = useLoad(() => api.students({ q, branch, unverified, limit: PAGE, offset }), [q, branch, unverified, offset]);

  return (
    <>
      <div className="page-head">
        <h1 tabIndex={-1}>Students</h1>
        <p className="muted">Verify CGPAs from official results; students can apply only after that.</p>
      </div>
      <div className="toolbar card" role="search">
        <label className="grow">
          <span className="sr-only">Search students</span>
          <input
            type="search"
            placeholder="Search by name, email or roll number"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <label className="inline">
          Branch
          <select
            value={branch}
            onChange={(e) => {
              setBranch(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All</option>
            {["CSE", "IT", "ECE", "EE", "ME", "CE"].map((b) => (
              <option key={b}>{b}</option>
            ))}
          </select>
        </label>
        <label className="inline check">
          <input
            type="checkbox"
            checked={unverified}
            onChange={(e) => {
              setParams(e.target.checked ? { unverified: "1" } : {});
              setOffset(0);
            }}
          />
          Only CGPA not verified
        </label>
      </div>
      <ErrorNote error={error} />
      {!data ? (
        <Loading />
      ) : data.items.length === 0 ? (
        <EmptyState title="No students found" />
      ) : (
        <div className="card table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Roll number</th>
                <th scope="col">Branch</th>
                <th scope="col">CGPA</th>
                <th scope="col">Skills</th>
                <th scope="col">Resume</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((s) => (
                <tr key={s.id}>
                  <th scope="row">
                    {s.name}
                    <span className="muted small block">{s.email}</span>
                  </th>
                  <td>{s.roll_no}</td>
                  <td>{s.branch}</td>
                  <td>
                    <CgpaCell student={s} onSaved={reload} />
                  </td>
                  <td className="small">{s.skills.join(", ")}</td>
                  <td>{s.resume_name ? "✓" : <span className="muted">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="pager">
            <button type="button" className="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
              ← Previous
            </button>
            <span className="muted">
              {offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}
            </span>
            <button type="button" className="ghost" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>
              Next →
            </button>
          </div>
        </div>
      )}
    </>
  );
}
