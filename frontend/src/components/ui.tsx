// Small shared pieces: status badges, the status timeline, KPI tiles, bar charts, loading and error states.

import { useEffect, useState, type ReactNode } from "react";
import type { Event, Status } from "../api";

export const STATUS_LABEL: Record<Status, string> = {
  applied: "Applied",
  shortlisted: "Shortlisted",
  interview: "Interview",
  offered: "Offered",
  rejected: "Not selected",
  withdrawn: "Withdrawn",
};

export function StatusBadge({ status }: { status: Status }) {
  return <span className={`badge badge-${status}`}>{STATUS_LABEL[status]}</span>;
}

const dateFmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
export const fmtDate = (s: string) => dateFmt.format(new Date(s));
export const fmtDateTime = (s: string) => dateTimeFmt.format(new Date(s));
export const fmtLpa = (v: number | null) => (v ? `₹${v.toFixed(1)} LPA` : "Not disclosed");

export function daysLeft(deadline: string): string {
  const d = Math.ceil((new Date(deadline + "T23:59:59").getTime() - Date.now()) / 86_400_000);
  return d < 0 ? "Closed" : d === 0 ? "Last day" : `${d} day${d === 1 ? "" : "s"} left`;
}

export function actorLabel(actor: string): string {
  if (actor.startsWith("student:")) return "Student";
  if (actor.startsWith("officer")) return "Placement office";
  return actor;
}

/** The application's journey: one row per status change, newest last. */
export function Timeline({ events }: { events: Event[] }) {
  return (
    <ol className="timeline" aria-label="Application history">
      {events.map((e, i) => (
        <li key={i} className={`tl-${e.to_status}`}>
          <span className="tl-dot" aria-hidden="true" />
          <div>
            <strong>{STATUS_LABEL[e.to_status as Status] ?? e.to_status}</strong>
            <span className="muted">
              {" "}
              · {fmtDateTime(e.at)} · {actorLabel(e.actor)}
            </span>
          </div>
        </li>
      ))}
    </ol>
  );
}

export function Kpi({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="kpi">
      <span className="kpi-value">{value}</span>
      <span className="kpi-label">{label}</span>
      {hint && <span className="kpi-hint">{hint}</span>}
    </div>
  );
}

/** Horizontal bars. The numbers are also written out, so the chart does not rely on colour or length alone. */
export function BarChart({ rows, label }: { rows: { name: string; value: number; extra?: string }[]; label: string }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <figure className="bars" aria-label={label}>
      {rows.map((r) => (
        <div className="bar-row" key={r.name}>
          <span className="bar-name" title={r.name}>
            {r.name}
          </span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${(r.value / max) * 100}%` }} />
          </span>
          <span className="bar-value">
            {r.value}
            {r.extra && <span className="muted"> {r.extra}</span>}
          </span>
        </div>
      ))}
    </figure>
  );
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return (
    <p className="loading" role="status">
      <span className="spinner" aria-hidden="true" /> {what}…
    </p>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p className="error-note" role="alert">
      {error instanceof Error ? error.message : String(error)}
    </p>
  );
}

/** Loads data for a page; `reload()` fetches again after a change. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]): { data: T | null; error: unknown; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    setError(null);
    load()
      .then((d) => live && setData(d))
      .catch((e) => live && setError(e));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, reload: () => setTick((t) => t + 1) };
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children && <p className="muted">{children}</p>}
    </div>
  );
}
