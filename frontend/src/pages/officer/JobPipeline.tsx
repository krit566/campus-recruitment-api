// The applicant pipeline for one job, as a kanban board. Cards move only along the workflow the API enforces:
// each card shows buttons for its allowed next steps (keyboard friendly), and cards can also be dragged onto a
// column that is a valid next step. The server re-checks every move (and the offer limit) and may refuse it.

import { useState, type DragEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api, newIdempotencyKey, saveBlob, type Application, type Status } from "../../api";
import { daysLeft, ErrorNote, fmtDateTime, fmtLpa, Loading, STATUS_LABEL, StatusBadge, useLoad } from "../../components/ui";

// "Closed" holds both final outcomes that are not offers; dropping a card there means "reject"
type Column = { key: string; label: string; statuses: Status[]; dropAs: Status };
const COLUMNS: Column[] = [
  { key: "applied", label: "Applied", statuses: ["applied"], dropAs: "applied" },
  { key: "shortlisted", label: "Shortlisted", statuses: ["shortlisted"], dropAs: "shortlisted" },
  { key: "interview", label: "Interview", statuses: ["interview"], dropAs: "interview" },
  { key: "offered", label: "Offered", statuses: ["offered"], dropAs: "offered" },
  { key: "closed", label: "Closed", statuses: ["rejected", "withdrawn"], dropAs: "rejected" },
];
// buttons on a card, in this order (forward moves first); withdrawing for a student is done on the detail page
const ACTIONS: { to: Status; label: string }[] = [
  { to: "shortlisted", label: "Shortlist" },
  { to: "interview", label: "To interview" },
  { to: "offered", label: "Make offer" },
  { to: "rejected", label: "Reject" },
];

export function JobPipeline() {
  const jid = Number(useParams().id);
  const { data, error, reload } = useLoad(
    () =>
      Promise.all([api.job(jid), api.jobStats(jid), api.applications({ job_id: jid }), api.workflow()]).then(([job, stats, apps, wf]) => ({
        job,
        stats,
        apps,
        wf,
      })),
    [jid],
  );
  const [moveError, setMoveError] = useState<unknown>(null);
  const [announce, setAnnounce] = useState("");
  const [dragging, setDragging] = useState<Application | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [q, setQ] = useState("");

  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading what="Loading pipeline" />;
  const { job, stats, apps, wf } = data;
  const allowed = (a: Application) => wf.transitions[a.status] ?? [];

  const move = async (a: Application, to: Status) => {
    if (to === "rejected" && !window.confirm(`Reject ${a.student_name}? This is final.`)) return;
    setMoveError(null);
    setBusyId(a.id);
    try {
      await api.setStatus(a.id, to, newIdempotencyKey());
      setAnnounce(`${a.student_name} moved to ${STATUS_LABEL[to]}.`);
      reload();
    } catch (e) {
      setMoveError(e);
    } finally {
      setBusyId(null);
    }
  };

  const buttons = (a: Application) => ACTIONS.filter((x) => allowed(a).includes(x.to));

  const onDrop = (to: Status) => (e: DragEvent) => {
    e.preventDefault();
    if (dragging && allowed(dragging).includes(to)) void move(dragging, to);
    setDragging(null);
  };

  const term = q.trim().toLowerCase();
  const visible = apps.filter((a) => !term || `${a.student_name} ${a.roll_no} ${a.branch}`.toLowerCase().includes(term));

  return (
    <>
      <p>
        <Link to="/officer/jobs">← All jobs</Link>
      </p>
      <div className="page-head row-between">
        <div>
          <h1 tabIndex={-1}>{job.title}</h1>
          <p className="muted">
            {job.company_name} · {job.location} · {fmtLpa(job.ctc_lpa)} · CGPA {job.min_cgpa}+ · {job.eligible_branches.join(", ")} ·{" "}
            {job.status === "open" ? daysLeft(job.deadline) : "closed"}
          </p>
        </div>
        <div className="row-actions">
          <button type="button" className="ghost" onClick={async () => saveBlob(await api.applicantsCsv(jid), `job-${jid}-applicants.csv`)}>
            Export CSV
          </button>
          {job.status === "open" && (
            <button
              type="button"
              className="ghost danger"
              onClick={async () => {
                if (window.confirm("Close this job to new applications?")) {
                  await api.closeJob(jid);
                  reload();
                }
              }}
            >
              Close job
            </button>
          )}
        </div>
      </div>
      <div className="kpis">
        <div className="kpi">
          <span className="kpi-value">{stats.total_applications}</span>
          <span className="kpi-label">Applicants</span>
        </div>
        <div className="kpi">
          <span className="kpi-value">{stats.openings}</span>
          <span className="kpi-label">Openings</span>
        </div>
        <div className="kpi">
          <span className="kpi-value">{stats.offers_left}</span>
          <span className="kpi-label">Offers left</span>
        </div>
        <div className="kpi">
          <span className={`kpi-value status-${job.status}`}>{job.status === "open" ? "Open" : "Closed"}</span>
          <span className="kpi-label">Status</span>
        </div>
      </div>
      <div className="toolbar card" role="search">
        <label className="grow">
          <span className="sr-only">Filter applicants</span>
          <input type="search" placeholder="Filter by name, roll number or branch" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <span className="muted small">Drag a card to a highlighted column, or use the buttons on the card.</span>
      </div>
      <ErrorNote error={moveError} />
      <p className="sr-only" role="status" aria-live="polite">
        {announce}
      </p>
      <div className="board" aria-label="Applicant pipeline">
        {COLUMNS.map((col) => {
          const cards = visible.filter((a) => col.statuses.includes(a.status));
          const canDrop = dragging ? allowed(dragging).includes(col.dropAs) : false;
          return (
            <section
              key={col.key}
              className={`column col-${col.key}${canDrop ? " drop-ok" : ""}`}
              aria-labelledby={`col-${col.key}`}
              onDragOver={(e) => canDrop && e.preventDefault()}
              onDrop={onDrop(col.dropAs)}
            >
              <h2 id={`col-${col.key}`}>
                {col.label} <span className="count">{cards.length}</span>
              </h2>
              <ul>
                {cards.map((a) => (
                  <li
                    key={a.id}
                    className={`kcard${busyId === a.id ? " busy" : ""}`}
                    draggable={buttons(a).length > 0}
                    onDragStart={() => setDragging(a)}
                    onDragEnd={() => setDragging(null)}
                  >
                    <Link to={`/officer/applications/${a.id}`} className="kname">
                      {a.student_name}
                    </Link>
                    <span className="muted small">
                      {a.branch} · CGPA {a.cgpa ?? "—"}
                    </span>
                    <span className="muted small nowrap">{a.roll_no}</span>
                    {col.key === "closed" && <StatusBadge status={a.status} />}
                    {a.interview_at && col.key === "interview" && <span className="small chip-time">📅 {fmtDateTime(a.interview_at)}</span>}
                    {buttons(a).length > 0 && (
                      <div className="kactions">
                        {buttons(a).map(({ to, label }) => (
                          <button
                            key={to}
                            type="button"
                            className={`mini${to === "rejected" ? " danger" : ""}`}
                            disabled={busyId === a.id}
                            onClick={() => move(a, to)}
                            aria-label={`${label}: ${a.student_name}`}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </>
  );
}
