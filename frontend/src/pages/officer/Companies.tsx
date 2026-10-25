import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { EmptyState, ErrorNote, Loading, useLoad } from "../../components/ui";

export function Companies() {
  const { data, error, reload } = useLoad(() => api.companies(), []);
  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");
  const [industry, setIndustry] = useState("");
  const [formError, setFormError] = useState<unknown>(null);

  const add = async (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    try {
      await api.createCompany({ name, website: website || null, industry });
      setName("");
      setWebsite("");
      setIndustry("");
      reload();
    } catch (err) {
      setFormError(err);
    }
  };

  return (
    <>
      <div className="page-head">
        <h1 tabIndex={-1}>Companies</h1>
        <p className="muted">Recruiters visiting campus this season.</p>
      </div>
      <section className="card" aria-labelledby="add-h">
        <h2 id="add-h">Add a company</h2>
        <form onSubmit={add} className="row3 align-end">
          <label>
            Name
            <input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            Website
            <input type="url" placeholder="https://" value={website} onChange={(e) => setWebsite(e.target.value)} />
          </label>
          <label>
            Industry
            <input value={industry} onChange={(e) => setIndustry(e.target.value)} />
          </label>
          <button type="submit">Add</button>
        </form>
        <ErrorNote error={formError} />
      </section>
      <ErrorNote error={error} />
      {!data ? (
        <Loading />
      ) : data.length === 0 ? (
        <EmptyState title="No companies yet" />
      ) : (
        <ul className="company-grid">
          {data.map((c) => (
            <li key={c.id} className="card company-card">
              <span className="company-chip" aria-hidden="true">
                {c.name.slice(0, 1)}
              </span>
              <div>
                <h2 className="job-title">{c.name}</h2>
                <p className="muted small">{c.industry || "Industry not set"}</p>
                <p className="small">
                  <Link to={`/officer/jobs?company=${c.id}`}>
                    {c.open_jobs} open job{c.open_jobs === 1 ? "" : "s"}
                  </Link>
                  {c.website && (
                    <>
                      {" "}
                      ·{" "}
                      <a href={c.website} target="_blank" rel="noreferrer noopener">
                        website
                      </a>
                    </>
                  )}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
