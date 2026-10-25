import { api } from "../../api";
import { EmptyState, ErrorNote, fmtDateTime, Loading, useLoad } from "../../components/ui";

const ICON: Record<string, string> = {
  interview: "📅",
  "status:shortlisted": "✅",
  "status:interview": "🗣️",
  "status:offered": "🎉",
  "status:rejected": "✖️",
  "status:withdrawn": "↩️",
};

export function Notifications() {
  const { data, error, reload } = useLoad(() => api.notifications(), []);
  if (error) return <ErrorNote error={error} />;
  if (!data) return <Loading />;

  return (
    <>
      <div className="page-head row-between">
        <div>
          <h1 tabIndex={-1}>Notifications</h1>
          <p className="muted">{data.unread} unread</p>
        </div>
        {data.unread > 0 && (
          <button type="button" className="ghost" onClick={() => api.readAll().then(reload)}>
            Mark all as read
          </button>
        )}
      </div>
      {data.items.length === 0 ? (
        <EmptyState title="No notifications">You will be told here when your applications move.</EmptyState>
      ) : (
        <ul className="card notes">
          {data.items.map((n) => (
            <li key={n.id} className={n.read_at ? "" : "unread"}>
              <span className="note-icon" aria-hidden="true">
                {ICON[n.kind] ?? "•"}
              </span>
              <div className="grow">
                <p>{n.message}</p>
                <span className="muted">{fmtDateTime(n.created_at)}</span>
              </div>
              {!n.read_at && (
                <button type="button" className="link" onClick={() => api.readNotification(n.id).then(reload)}>
                  Mark read
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
