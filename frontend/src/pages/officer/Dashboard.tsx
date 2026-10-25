import { Link } from "react-router-dom";
import { api, type Status } from "../../api";
import { BarChart, ErrorNote, Kpi, Loading, STATUS_LABEL, useLoad } from "../../components/ui";

const FUNNEL: Status[] = ["applied", "shortlisted", "interview", "offered", "rejected", "withdrawn"];

export function Dashboard() {
  const { data: o, error } = useLoad(() => api.overview(), []);
  if (error) return <ErrorNote error={error} />;
  if (!o) return <Loading what="Loading dashboard" />;

  return (
    <>
      <div className="page-head">
        <h1 tabIndex={-1}>Placement dashboard</h1>
        <p className="muted">Live numbers from the database. Placement rate = students with at least one offer ÷ all registered students.</p>
      </div>
      <div className="kpis six">
        <Kpi label="Students" value={o.students} hint={o.students_unverified ? `${o.students_unverified} CGPA to verify` : "all verified"} />
        <Kpi label="Open jobs" value={o.open_jobs} />
        <Kpi label="Applications" value={o.applications} />
        <Kpi label="Offers" value={o.offers} />
        <Kpi label="Placement rate" value={`${Math.round(o.placement_rate * 100)}%`} hint={`${o.placed_students} placed`} />
        <Kpi label="Upcoming interviews" value={o.upcoming_interviews} />
      </div>
      {o.students_unverified > 0 && (
        <p className="banner warn" role="note">
          {o.students_unverified} student{o.students_unverified === 1 ? " is" : "s are"} waiting for CGPA verification and cannot apply yet.{" "}
          <Link to="/officer/students?unverified=1">Verify now</Link>
        </p>
      )}
      <div className="grid2">
        <section className="card" aria-labelledby="apj-h">
          <h2 id="apj-h">Applications per job</h2>
          <BarChart
            label="Applications per job, with offers"
            rows={o.applications_per_job.map((j) => ({ name: `${j.title} · ${j.company_name}`, value: j.applications, extra: `(${j.offers} offers)` }))}
          />
        </section>
        <section className="card" aria-labelledby="fun-h">
          <h2 id="fun-h">Where applications are</h2>
          <BarChart label="Applications by status" rows={FUNNEL.map((s) => ({ name: STATUS_LABEL[s], value: o.status_funnel[s] ?? 0 }))} />
        </section>
      </div>
      <section className="card" aria-labelledby="br-h">
        <h2 id="br-h">Placements by branch</h2>
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Branch</th>
              <th scope="col">Students</th>
              <th scope="col">Placed</th>
              <th scope="col" className="w-50">
                Rate
              </th>
            </tr>
          </thead>
          <tbody>
            {o.branch_placements.map((b) => {
              const rate = b.students ? b.placed / b.students : 0;
              return (
                <tr key={b.branch}>
                  <th scope="row">{b.branch}</th>
                  <td>{b.students}</td>
                  <td>{b.placed}</td>
                  <td>
                    <span className="meter" aria-hidden="true">
                      <span style={{ width: `${rate * 100}%` }} />
                    </span>{" "}
                    {Math.round(rate * 100)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </>
  );
}
