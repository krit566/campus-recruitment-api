import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, newIdempotencyKey, type Application, type Event } from "../../api";
import { EmptyState, ErrorNote, fmtDate, fmtDateTime, Loading, StatusBadge, Timeline, useLoad } from "../../components/ui";

const STEPS = ["applied", "shortlisted", "interview", "offered"] as const;

/** A compact progress bar: applied → shortlisted → interview → offered. */
function Progress({ status }: { status: Application["status"] }) {
  const reached = STEPS.indexOf(status as (typeof STEPS)[number]);
  const ended = status === "rejected" || status === "withdrawn";
  return (
    <ol className={`progress${ended ? " ended" : ""}`} aria-label="Progress">
      {STEPS.map((s, i) => (
        <li key={s} className={i <= reached ? "done" : ""} aria-current={i === reached ? "step" : undefined}>
          {s}
        </li>
      ))}
    </ol>
  );
}

function ApplicationCard({ app, onChange, startOpen }: { app: Application; onChange: () => void; startOpen: boolean }) {
  const [events, setEvents] = useState<Event[] | null>(null);
  const [open, setOpen] = useState(startOpen);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const canWithdraw = app.status === "applied" || app.status === "shortlisted";

  // history is fetched the first time the card is opened
  useEffect(() => {
    if (open && !events) api.history(app.id).then(setEvents).catch(setError);
  }, [open, events, app.id]);
  const toggle = () => setOpen(!open);
  const withdraw = async () => {
    if (!window.confirm(`Withdraw your application for ${app.job_title}? This cannot be undone.`)) return;
    setBusy(true);
    try {
      await api.setStatus(app.id, "withdrawn", newIdempotencyKey());
      onChange();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="card app-card">
      <div className="app-head">
        <div>
          <h2 className="job-title">
            <Link to={`/student/jobs/${app.job_id}`}>{app.job_title}</Link>
          </h2>
          <p className="muted">
            {app.company_name} · applied {fmtDate(app.created_at)}
          </p>
        </div>
        <StatusBadge status={app.status} />
      </div>
      <Progress status={app.status} />
      {app.interview_at && app.status === "interview" && (
        <p className="banner info">Interview: {fmtDateTime(app.interview_at)}. Details are in your notifications.</p>
      )}
      <div className="row-actions">
        <button type="button" className="ghost" aria-expanded={open} onClick={toggle}>
          {open ? "Hide history" : "Show history"}
        </button>
        {canWithdraw && (
          <button type="button" className="danger ghost" onClick={withdraw} disabled={busy}>
            Withdraw
          </button>
        )}
      </div>
      {open && (events ? <Timeline events={events} /> : <Loading what="Loading history" />)}
      <ErrorNote error={error} />
    </li>
  );
}

export function MyApplications() {
  const { data, error, reload } = useLoad(() => api.applications({}), []);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const sorted = [...data].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
  return (
    <>
      <div className="page-head">
        <h1 tabIndex={-1}>My applications</h1>
        <p className="muted">{data.length} in total. Every status change is recorded with who made it and when.</p>
      </div>
      {sorted.length === 0 ? (
        <EmptyState title="No applications yet">
          <Link to="/student/jobs">Find jobs</Link> you are eligible for.
        </EmptyState>
      ) : (
        <ul className="stack-list">
          {sorted.map((a, i) => (
            <ApplicationCard key={a.id} app={a} onChange={reload} startOpen={i === 0} />
          ))}
        </ul>
      )}
    </>
  );
}
