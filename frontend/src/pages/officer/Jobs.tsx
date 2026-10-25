import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type Company } from "../../api";
import { daysLeft, EmptyState, ErrorNote, fmtLpa, Loading, useLoad } from "../../components/ui";

const BRANCHES = ["CSE", "IT", "ECE", "EE", "ME", "CE"];

function NewJobForm({ companies, onCreated }: { companies: Company[]; onCreated: () => void }) {
  const inMonth = new Date(Date.now() + 30 * 86_400_000).toISOString().slice(0, 10);
  const empty = { company_id: companies[0]?.id ?? 0, title: "", location: "", ctc_lpa: "", min_cgpa: "7", openings: "1", deadline: inMonth, description: "" };
  const [f, setF] = useState(empty);
  const [branches, setBranches] = useState<string[]>(["CSE", "IT"]);
  const [error, setError] = useState<unknown>(null);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setF({ ...f, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.createJob({
        ...f,
        company_id: Number(f.company_id),
        ctc_lpa: f.ctc_lpa ? Number(f.ctc_lpa) : null,
        min_cgpa: Number(f.min_cgpa),
        openings: Number(f.openings),
        eligible_branches: branches,
      });
      setF(empty);
      onCreated();
    } catch (err) {
      setError(err);
    }
  };

  if (companies.length === 0)
    return (
      <p className="muted">
        Add a <Link to="/officer/companies">company</Link> first.
      </p>
    );
  return (
    <form onSubmit={submit} className="stack">
      <div className="row2">
        <label>
          Company
          <select value={f.company_id} onChange={set("company_id")}>
            {companies.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Title
          <input required minLength={2} value={f.title} onChange={set("title")} />
        </label>
      </div>
      <div className="row3">
        <label>
          Location
          <input value={f.location} onChange={set("location")} />
        </label>
        <label>
          Pay (LPA)
          <input type="number" step="0.5" min="0.5" value={f.ctc_lpa} onChange={set("ctc_lpa")} />
        </label>
        <label>
          Openings
          <input type="number" min="1" required value={f.openings} onChange={set("openings")} />
        </label>
      </div>
      <div className="row2">
        <label>
          Minimum CGPA
          <input type="number" step="0.1" min="0" max="10" value={f.min_cgpa} onChange={set("min_cgpa")} />
        </label>
        <label>
          Deadline
          <input type="date" required value={f.deadline} onChange={set("deadline")} />
        </label>
      </div>
      <fieldset className="branches">
        <legend>Eligible branches</legend>
        {BRANCHES.map((b) => (
          <label key={b} className="check">
            <input
              type="checkbox"
              checked={branches.includes(b)}
              onChange={(e) => setBranches(e.target.checked ? [...branches, b] : branches.filter((x) => x !== b))}
            />
            {b}
          </label>
        ))}
      </fieldset>
      <label>
        Description
        <textarea rows={3} value={f.description} onChange={set("description")} />
      </label>
      <ErrorNote error={error} />
      <button type="submit">Post job</button>
    </form>
  );
}

export function OfficerJobs() {
  const [params] = useSearchParams();
  const companyId = params.get("company") ?? undefined; // set when arriving from the Companies page
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [showForm, setShowForm] = useState(false);
  const { data, error, reload } = useLoad(
    () =>
      Promise.all([api.jobs({ status, q, company_id: companyId, limit: 100 }), api.companies()]).then(([jobs, companies]) => ({ jobs, companies })),
    [status, q, companyId],
  );

  return (
    <>
      <div className="page-head row-between">
        <div>
          <h1 tabIndex={-1}>Jobs</h1>
          <p className="muted">Open a job to manage its applicant pipeline.</p>
        </div>
        <button type="button" onClick={() => setShowForm(!showForm)} aria-expanded={showForm}>
          {showForm ? "Cancel" : "+ Post a job"}
        </button>
      </div>
      {showForm && data && (
        <section className="card" aria-labelledby="new-h">
          <h2 id="new-h">New job</h2>
          <NewJobForm
            companies={data.companies}
            onCreated={() => {
              setShowForm(false);
              reload();
            }}
          />
        </section>
      )}
      <div className="toolbar card" role="search">
        <label className="grow">
          <span className="sr-only">Search jobs</span>
          <input type="search" placeholder="Search by role, company or city" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <label className="inline">
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All</option>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
          </select>
        </label>
      </div>
      <ErrorNote error={error} />
      {!data ? (
        <Loading />
      ) : data.jobs.items.length === 0 ? (
        <EmptyState title="No jobs found" />
      ) : (
        <div className="card table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Role</th>
                <th scope="col">Company</th>
                <th scope="col">Pay</th>
                <th scope="col">Branches</th>
                <th scope="col">Applicants</th>
                <th scope="col">Deadline</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.jobs.items.map((j) => (
                <tr key={j.id}>
                  <th scope="row">
                    <Link to={`/officer/jobs/${j.id}`}>{j.title}</Link>
                  </th>
                  <td>{j.company_name}</td>
                  <td>{fmtLpa(j.ctc_lpa)}</td>
                  <td>{j.eligible_branches.join(", ")}</td>
                  <td>
                    {j.applications} / {j.openings} openings
                  </td>
                  <td>{daysLeft(j.deadline)}</td>
                  <td>
                    <span className={`pill ${j.status === "open" ? "ok" : ""}`}>{j.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
