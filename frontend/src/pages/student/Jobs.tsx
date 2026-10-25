import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Job, type Student } from "../../api";
import { useAuth } from "../../auth";
import { daysLeft, EmptyState, ErrorNote, fmtLpa, Loading, StatusBadge, useLoad } from "../../components/ui";

/** Why a student cannot apply (empty = eligible). The API checks the same rules again when they apply. */
export function ineligibility(job: Job, s: Student): string {
  if (!job.eligible_branches.includes(s.branch)) return `Open to ${job.eligible_branches.join(", ")} only`;
  if (s.cgpa === null) return "Needs your verified CGPA";
  if (s.cgpa < job.min_cgpa) return `Needs CGPA ${job.min_cgpa}+`;
  return "";
}

export function StudentJobs() {
  const { me } = useAuth();
  const sid = me!.student_id!;
  const [q, setQ] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [sort, setSort] = useState<"deadline" | "ctc">("deadline");
  const { data, error } = useLoad(
    () =>
      Promise.all([api.student(sid), api.jobs({ status: "open", limit: 100 }), api.applications({})]).then(([student, jobs, apps]) => ({
        student,
        jobs: jobs.items,
        apps,
      })),
    [sid],
  );

  const rows = useMemo(() => {
    if (!data) return [];
    const term = q.trim().toLowerCase();
    return data.jobs
      .map((j) => ({ job: j, why: ineligibility(j, data.student), app: data.apps.find((a) => a.job_id === j.id) }))
      .filter((r) => showAll || !r.why)
      .filter((r) => !term || [r.job.title, r.job.company_name ?? "", r.job.location].some((t) => t.toLowerCase().includes(term)))
      .sort((a, b) => (sort === "ctc" ? (b.job.ctc_lpa ?? 0) - (a.job.ctc_lpa ?? 0) : a.job.deadline.localeCompare(b.job.deadline)));
  }, [data, q, showAll, sort]);

  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading what="Loading jobs" />;
  const eligibleCount = data.jobs.filter((j) => !ineligibility(j, data.student)).length;

  return (
    <>
      <div className="page-head">
        <h1 tabIndex={-1}>Jobs</h1>
        <p className="muted">
          {eligibleCount} of {data.jobs.length} open jobs match your branch and CGPA.
        </p>
      </div>
      <div className="toolbar card" role="search">
        <label className="grow">
          <span className="sr-only">Search jobs</span>
          <input type="search" placeholder="Search by role, company or city" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
        <label className="inline">
          Sort by
          <select value={sort} onChange={(e) => setSort(e.target.value as "deadline" | "ctc")}>
            <option value="deadline">Deadline</option>
            <option value="ctc">Pay (highest first)</option>
          </select>
        </label>
        <label className="inline check">
          <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
          Show jobs I am not eligible for
        </label>
      </div>
      {rows.length === 0 ? (
        <EmptyState title="No jobs match">Try another search{showAll ? "" : ", or show jobs you are not eligible for"}.</EmptyState>
      ) : (
        <ul className="job-grid">
          {rows.map(({ job, why, app }) => (
            <li key={job.id} className={`card job-card${why ? " dim" : ""}`}>
              <div className="job-top">
                <span className="company-chip" aria-hidden="true">
                  {(job.company_name ?? "?").slice(0, 1)}
                </span>
                <div>
                  <h2 className="job-title">
                    <Link to={`/student/jobs/${job.id}`}>{job.title}</Link>
                  </h2>
                  <p className="muted">{job.company_name}</p>
                </div>
              </div>
              <dl className="facts">
                <div>
                  <dt>Pay</dt>
                  <dd>{fmtLpa(job.ctc_lpa)}</dd>
                </div>
                <div>
                  <dt>Location</dt>
                  <dd>{job.location || "—"}</dd>
                </div>
                <div>
                  <dt>Min CGPA</dt>
                  <dd>{job.min_cgpa}</dd>
                </div>
              </dl>
              <div className="job-foot">
                <span className="deadline">{daysLeft(job.deadline)}</span>
                {app ? <StatusBadge status={app.status} /> : why ? <span className="why">{why}</span> : <span className="pill ok">Eligible</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
