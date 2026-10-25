import { Link } from "react-router-dom";
import { api } from "../../api";
import { useAuth } from "../../auth";
import { daysLeft, EmptyState, ErrorNote, fmtDateTime, Kpi, Loading, StatusBadge, useLoad } from "../../components/ui";

export function StudentHome() {
  const { me } = useAuth();
  const sid = me!.student_id!;
  const { data, error } = useLoad(
    () =>
      Promise.all([api.student(sid), api.applications({}), api.interviews(), api.notifications(), api.eligibleJobs(sid)]).then(
        ([student, apps, interviews, notes, jobs]) => ({ student, apps, interviews, notes, jobs }),
      ),
    [sid],
  );
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const { student, apps, interviews, notes, jobs } = data;
  const active = apps.filter((a) => ["applied", "shortlisted", "interview"].includes(a.status)).length;
  const offers = apps.filter((a) => a.status === "offered");
  const appliedJobs = new Set(apps.map((a) => a.job_id));
  const closingSoon = jobs.filter((j) => !appliedJobs.has(j.id)).slice(0, 3);

  return (
    <>
      <div className="page-head">
        <h1 tabIndex={-1}>Hi, {student.name.split(" ")[0]}</h1>
        <p className="muted">
          {student.branch} · {student.roll_no} · Class of {student.graduation_year}
        </p>
      </div>
      {student.cgpa === null && (
        <p className="banner warn" role="note">
          Your CGPA has not been verified by the placement office yet, so you cannot apply to jobs. This usually happens within a few
          working days of registering.
        </p>
      )}
      {!student.resume_name && (
        <p className="banner info" role="note">
          Recruiters see your resume with your application. <Link to="/student/profile">Upload your resume (PDF)</Link>.
        </p>
      )}
      {offers.length > 0 && (
        <p className="banner ok" role="note">
          🎉 You have {offers.length === 1 ? "an offer" : `${offers.length} offers`}:{" "}
          {offers.map((o) => `${o.job_title} at ${o.company_name}`).join(", ")}.
        </p>
      )}
      <div className="kpis">
        <Kpi label="Applications" value={apps.length} />
        <Kpi label="In progress" value={active} />
        <Kpi label="Upcoming interviews" value={interviews.length} />
        <Kpi label="Jobs open to you" value={jobs.length} />
      </div>
      <div className="grid2">
        <section className="card" aria-labelledby="up-h">
          <h2 id="up-h">Upcoming interviews</h2>
          {interviews.length === 0 ? (
            <EmptyState title="No interviews scheduled">When you reach the interview round, the slot appears here.</EmptyState>
          ) : (
            <ul className="list">
              {interviews.map((i) => (
                <li key={i.id}>
                  <strong>{fmtDateTime(i.starts_at)}</strong> · {i.job_title} at {i.company_name}
                  <span className="muted">
                    {" "}
                    · {i.mode === "online" ? "Online" : i.location || "On campus"} · {i.panel}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="card" aria-labelledby="new-h">
          <h2 id="new-h">
            Latest updates{" "}
            {notes.unread > 0 && (
              <span className="pill" aria-label={`${notes.unread} unread`}>
                {notes.unread} new
              </span>
            )}
          </h2>
          {notes.items.length === 0 ? (
            <EmptyState title="Nothing yet">Updates on your applications appear here.</EmptyState>
          ) : (
            <ul className="list">
              {notes.items.slice(0, 4).map((n) => (
                <li key={n.id} className={n.read_at ? "" : "unread"}>
                  {n.message} <span className="muted">· {fmtDateTime(n.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
          <Link to="/student/notifications">All notifications →</Link>
        </section>
      </div>
      <section className="card" aria-labelledby="soon-h">
        <h2 id="soon-h">Open to you, closing soon</h2>
        {closingSoon.length === 0 ? (
          <EmptyState title="No new jobs to apply to">You have applied to every job you are eligible for, or none are open.</EmptyState>
        ) : (
          <ul className="job-mini">
            {closingSoon.map((j) => (
              <li key={j.id}>
                <Link to={`/student/jobs/${j.id}`}>
                  <strong>{j.title}</strong>
                </Link>
                <span className="muted">
                  {j.company_name} · {j.location}
                </span>
                <span className="deadline">{daysLeft(j.deadline)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="card" aria-labelledby="recent-h">
        <h2 id="recent-h">Recent applications</h2>
        {apps.length === 0 ? (
          <EmptyState title="No applications yet">
            <Link to="/student/jobs">Browse jobs</Link> you are eligible for.
          </EmptyState>
        ) : (
          <ul className="list">
            {apps.slice(-4).reverse().map((a) => (
              <li key={a.id}>
                {a.job_title} at {a.company_name} <StatusBadge status={a.status} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
