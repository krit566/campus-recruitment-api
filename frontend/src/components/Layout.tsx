import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

const STUDENT_NAV = [
  { to: "/student", label: "Home", end: true },
  { to: "/student/jobs", label: "Jobs" },
  { to: "/student/applications", label: "My applications" },
  { to: "/student/profile", label: "Profile" },
];
const OFFICER_NAV = [
  { to: "/officer", label: "Dashboard", end: true },
  { to: "/officer/jobs", label: "Jobs" },
  { to: "/officer/students", label: "Students" },
  { to: "/officer/companies", label: "Companies" },
  { to: "/officer/interviews", label: "Interviews" },
];

export function Layout() {
  const { me, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [unread, setUnread] = useState(0);
  const nav = me?.role === "officer" ? OFFICER_NAV : STUDENT_NAV;

  // unread count for the bell; refreshed on every page change
  useEffect(() => {
    if (me?.role === "student") api.notifications().then((n) => setUnread(n.unread)).catch(() => undefined);
  }, [me, location.pathname]);

  // move focus to the page heading after navigation, so screen-reader users hear where they are
  useEffect(() => {
    document.querySelector<HTMLElement>("main h1")?.focus();
  }, [location.pathname]);

  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <div className="topbar-in">
          <NavLink to={me?.role === "officer" ? "/officer" : "/student"} className="brand-link">
            <span className="logo" aria-hidden="true">
              P
            </span>
            PlaceRight
          </NavLink>
          <nav aria-label="Main">
            <ul>
              {nav.map((n) => (
                <li key={n.to}>
                  <NavLink to={n.to} end={n.end}>
                    {n.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          <div className="who">
            {me?.role === "student" && (
              <NavLink to="/student/notifications" className="bell" aria-label={`Notifications, ${unread} unread`}>
                <span aria-hidden="true">🔔</span>
                {unread > 0 && (
                  <span className="bell-count" aria-hidden="true">
                    {unread}
                  </span>
                )}
              </NavLink>
            )}
            <span className="who-name">
              {me?.name ?? me?.email}
              <span className="who-role">{me?.role === "officer" ? "Placement office" : "Student"}</span>
            </span>
            <button
              type="button"
              className="ghost"
              onClick={() => {
                logout();
                navigate("/login");
              }}
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main id="main" className="page">
        <Outlet />
      </main>
      <footer className="foot">PlaceRight · demo data is fictional</footer>
    </>
  );
}
