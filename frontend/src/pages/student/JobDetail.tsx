import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, newIdempotencyKey, type Application } from "../../api";
import { useAuth } from "../../auth";
import { daysLeft, ErrorNote, fmtDate, fmtLpa, Loading, StatusBadge, useLoad } from "../../components/ui";
import { ineligibility } from "./Jobs";

export function JobDetail() {
  const { id } = useParams();
  const jid = Number(id);
  const { me } = useAuth();
  const sid = me!.student_id!;
  const { data, error } = useLoad(
    () =>
      Promise.all([api.job(jid), api.student(sid), api.applications({ job_id: jid })]).then(([job, student, apps]) => ({
        job,
        student,
        existing: apps[0] as Application | undefined,
      })),
    [jid, sid],
  );
  const [applied, setApplied] = useState<Application | null>(null);
  const [applyError, setApplyError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  // one key for this page's "Apply" action: if the network drops and the student clicks again, it is the same request
  const key = useRef(newIdempotencyKey());

  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;
  const { job, student } = data;
  const app = applied ?? data.existing;
  const why = ineligibility(job, student);

  const apply = async () => {
    setBusy(true);
    setApplyError(null);
    try {
      setApplied(await api.apply(sid, jid, key.current));
    } catch (e) {
      setApplyError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <p>
        <Link to="/student/jobs">← All jobs</Link>
      </p>
      <div className="page-head">
        <h1 tabIndex={-1}>{job.title}</h1>
        <p className="muted">
          {job.company_name} · {job.location || "Location to be confirmed"}
        </p>
      </div>
      <div className="grid2 wide-left">
        <section className="card" aria-labelledby="about-h">
          <h2 id="about-h">About the role</h2>
          <p className="prewrap">{job.description || "No description provided."}</p>
          <dl className="facts">
            <div>
              <dt>Pay</dt>
              <dd>{fmtLpa(job.ctc_lpa)}</dd>
            </div>
            <div>
              <dt>Openings</dt>
              <dd>{job.openings}</dd>
            </div>
            <div>
              <dt>Apply by</dt>
              <dd>
                {fmtDate(job.deadline)} ({daysLeft(job.deadline)})
              </dd>
            </div>
          </dl>
        </section>
        <aside className="card" aria-labelledby="elig-h">
          <h2 id="elig-h">Eligibility</h2>
          <ul className="checks">
            <li className={job.eligible_branches.includes(student.branch) ? "pass" : "fail"}>
              Branch: {job.eligible_branches.join(", ")} (you: {student.branch})
            </li>
            <li className={student.cgpa !== null && student.cgpa >= job.min_cgpa ? "pass" : "fail"}>
              CGPA {job.min_cgpa}+ (you: {student.cgpa ?? "not verified yet"})
            </li>
            <li className={job.status === "open" ? "pass" : "fail"}>Job is {job.status === "open" ? "accepting applications" : "closed"}</li>
          </ul>
          {app ? (
            <p className="banner ok" role="status">
              Applied · <StatusBadge status={app.status} /> <Link to="/student/applications">Track it</Link>
            </p>
          ) : (
            <>
              <button type="button" onClick={apply} disabled={busy || Boolean(why) || job.status !== "open"}>
                {busy ? "Applying…" : "Apply now"}
              </button>
              {why && <p className="hint">{why}</p>}
              {!student.resume_name && !why && (
                <p className="hint">
                  Tip: <Link to="/student/profile">upload your resume</Link> first so recruiters can see it.
                </p>
              )}
            </>
          )}
          <ErrorNote error={applyError} />
        </aside>
      </div>
    </>
  );
}
