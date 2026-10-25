import { Link } from "react-router-dom";
import { api, type Interview } from "../../api";
import { EmptyState, ErrorNote, Loading, useLoad } from "../../components/ui";

const day = new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long" });
const time = new Intl.DateTimeFormat("en-IN", { hour: "numeric", minute: "2-digit" });

export function Interviews() {
  const { data, error } = useLoad(() => api.interviews(), []);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;

  // group by calendar day
  const days = new Map<string, Interview[]>();
  for (const i of data) {
    const k = day.format(new Date(i.starts_at));
    days.set(k, [...(days.get(k) ?? []), i]);
  }

  return (
    <>
      <div className="page-head">
        <h1 tabIndex={-1}>Upcoming interviews</h1>
        <p className="muted">
          {data.length} scheduled. A panel cannot be booked twice at the same time, and neither can a student.
        </p>
      </div>
      {data.length === 0 ? (
        <EmptyState title="No interviews scheduled">Schedule them from an application in the interview stage.</EmptyState>
      ) : (
        [...days.entries()].map(([d, list]) => (
          <section key={d} className="card" aria-label={d}>
            <h2>{d}</h2>
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Student</th>
                  <th scope="col">Role</th>
                  <th scope="col">Panel</th>
                  <th scope="col">Where</th>
                </tr>
              </thead>
              <tbody>
                {list.map((i) => (
                  <tr key={i.id}>
                    <td>
                      {time.format(new Date(i.starts_at))}–{time.format(new Date(i.ends_at))}
                    </td>
                    <th scope="row">
                      <Link to={`/officer/applications/${i.application_id}`}>{i.student_name}</Link>
                    </th>
                    <td>
                      {i.job_title} <span className="muted">· {i.company_name}</span>
                    </td>
                    <td>{i.panel}</td>
                    <td>{i.mode === "online" ? "Online" : i.location || "On campus"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))
      )}
    </>
  );
}
