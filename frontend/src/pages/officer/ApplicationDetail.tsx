import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, newIdempotencyKey, saveBlob, type Interview, type Status } from "../../api";
import { ErrorNote, fmtDateTime, Loading, STATUS_LABEL, StatusBadge, Timeline, useLoad } from "../../components/ui";

const pad = (n: number) => String(n).padStart(2, "0");

function ScheduleForm({ appId, current, onDone }: { appId: number; current: Interview | null; onDone: () => void }) {
  const start = current ? new Date(current.starts_at) : new Date(Date.now() + 2 * 86_400_000);
  const [date, setDate] = useState(`${start.getFullYear()}-${pad(start.getMonth() + 1)}-${pad(start.getDate())}`);
  const [time, setTime] = useState(current ? `${pad(start.getHours())}:${pad(start.getMinutes())}` : "10:00");
  const [minutes, setMinutes] = useState(current ? Math.round((+new Date(current.ends_at) - +start) / 60000) : 30);
  const [mode, setMode] = useState<"online" | "onsite">(current?.mode ?? "online");
  const [location, setLocation] = useState(current?.location ?? "");
  const [panel, setPanel] = useState(current?.panel ?? "");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      // the date and time are in the officer's own time zone; toISOString() sends an exact instant to the API
      const startsAt = new Date(`${date}T${time}`).toISOString();
      await api.schedule(appId, { starts_at: startsAt, duration_minutes: minutes, mode, location, panel });
      onDone();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="stack">
      <div className="row2">
        <label>
          Date
          <input type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label>
          Start time
          <input type="time" required value={time} onChange={(e) => setTime(e.target.value)} />
        </label>
      </div>
      <div className="row2">
        <label>
          Length
          <select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
            {[15, 30, 45, 60, 90].map((m) => (
              <option key={m} value={m}>
                {m} minutes
              </option>
            ))}
          </select>
        </label>
        <label>
          Mode
          <select value={mode} onChange={(e) => setMode(e.target.value as "online" | "onsite")}>
            <option value="online">Online</option>
            <option value="onsite">On campus</option>
          </select>
        </label>
      </div>
      <label>
        Panel (interviewer)
        <input required minLength={2} value={panel} onChange={(e) => setPanel(e.target.value)} placeholder="e.g. Panel A (Tech)" />
      </label>
      <label>
        {mode === "online" ? "Meeting link" : "Room"}
        <input value={location} onChange={(e) => setLocation(e.target.value)} />
      </label>
      {error instanceof ApiError && error.status === 409 ? (
        <p className="error-note" role="alert">
          Clash: {error.message}. Pick another time or panel.
        </p>
      ) : (
        <ErrorNote error={error} />
      )}
      <button type="submit" disabled={busy}>
        {busy ? "Saving…" : current ? "Reschedule" : "Schedule interview"}
      </button>
    </form>
  );
}

export function ApplicationDetail() {
  const aid = Number(useParams().id);
  const { data, error, reload } = useLoad(
    () =>
      Promise.all([api.application(aid), api.history(aid), api.workflow(), api.interview(aid).catch(() => null)]).then(
        async ([app, events, wf, interview]) => ({ app, events, wf, interview, student: await api.student(app.student_id) }),
      ),
    [aid],
  );
  const [actionError, setActionError] = useState<unknown>(null);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const { app, events, wf, interview, student } = data;
  const next = wf.transitions[app.status] ?? [];

  const move = async (to: Status) => {
    if (to === "rejected" && !window.confirm(`Reject ${app.student_name}? This is final.`)) return;
    setActionError(null);
    try {
      await api.setStatus(aid, to, newIdempotencyKey());
      reload();
    } catch (e) {
      setActionError(e);
    }
  };

  return (
    <>
      <p>
        <Link to={`/officer/jobs/${app.job_id}`}>← {app.job_title} pipeline</Link>
      </p>
      <div className="page-head row-between">
        <div>
          <h1 tabIndex={-1}>{student.name}</h1>
          <p className="muted">
            Applied for {app.job_title} at {app.company_name}
          </p>
        </div>
        <StatusBadge status={app.status} />
      </div>
      <div className="grid2">
        <section className="card" aria-labelledby="cand-h">
          <h2 id="cand-h">Candidate</h2>
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
              <dd>{student.cgpa ?? "Not verified"}</dd>
            </div>
          </dl>
          <p>
            <a href={`mailto:${student.email}`}>{student.email}</a>
          </p>
          <p className="chips">
            {student.skills.map((s) => (
              <span key={s} className="chip">
                {s}
              </span>
            ))}
          </p>
          {student.resume_name ? (
            <button type="button" className="ghost" onClick={async () => saveBlob(await api.resumeBlob(student.id), student.resume_name!)}>
              📄 Download resume
            </button>
          ) : (
            <p className="muted">No resume uploaded.</p>
          )}
        </section>
        <section className="card" aria-labelledby="hist-h">
          <h2 id="hist-h">History</h2>
          <Timeline events={events} />
          {next.length > 0 && (
            <div className="row-actions">
              {next.map((to) => (
                <button key={to} type="button" className={to === "rejected" || to === "withdrawn" ? "ghost danger" : ""} onClick={() => move(to)}>
                  Move to {STATUS_LABEL[to]}
                </button>
              ))}
            </div>
          )}
          <ErrorNote error={actionError} />
        </section>
      </div>
      <section className="card" aria-labelledby="int-h">
        <h2 id="int-h">Interview</h2>
        {interview && (
          <p className="banner info">
            Scheduled: <strong>{fmtDateTime(interview.starts_at)}</strong> to {fmtDateTime(interview.ends_at)} ·{" "}
            {interview.mode === "online" ? "Online" : interview.location || "On campus"} · {interview.panel}{" "}
            <button
              type="button"
              className="link danger"
              onClick={async () => {
                await api.cancelInterview(aid);
                reload();
              }}
            >
              Cancel
            </button>
          </p>
        )}
        {app.status === "interview" ? (
          <ScheduleForm appId={aid} current={interview} onDone={reload} />
        ) : (
          <p className="muted">Move the application to the interview stage to schedule a slot.</p>
        )}
      </section>
    </>
  );
}
