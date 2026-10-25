import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import type { Role } from "./api";
import { useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { Login, Register } from "./pages/Auth";
import { ApplicationDetail } from "./pages/officer/ApplicationDetail";
import { Companies } from "./pages/officer/Companies";
import { Dashboard } from "./pages/officer/Dashboard";
import { Interviews } from "./pages/officer/Interviews";
import { JobPipeline } from "./pages/officer/JobPipeline";
import { OfficerJobs } from "./pages/officer/Jobs";
import { Students } from "./pages/officer/Students";
import { MyApplications } from "./pages/student/Applications";
import { StudentHome } from "./pages/student/Home";
import { JobDetail } from "./pages/student/JobDetail";
import { StudentJobs } from "./pages/student/Jobs";
import { Notifications } from "./pages/student/Notifications";
import { Profile } from "./pages/student/Profile";

/** Shows the page only to the right role; everyone else is sent to their own home or the login page.
 *  (This is for navigation only: the API checks the role on every request.) */
function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { me, loading } = useAuth();
  if (loading) return <Loading what="Signing you in" />;
  if (!me) return <Navigate to="/login" replace />;
  if (me.role !== role) return <Navigate to={me.role === "officer" ? "/officer" : "/student"} replace />;
  return <>{children}</>;
}

function Home() {
  const { me, loading } = useAuth();
  if (loading) return <Loading />;
  return <Navigate to={!me ? "/login" : me.role === "officer" ? "/officer" : "/student"} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route
        path="/student"
        element={
          <RequireRole role="student">
            <Layout />
          </RequireRole>
        }
      >
        <Route index element={<StudentHome />} />
        <Route path="jobs" element={<StudentJobs />} />
        <Route path="jobs/:id" element={<JobDetail />} />
        <Route path="applications" element={<MyApplications />} />
        <Route path="profile" element={<Profile />} />
        <Route path="notifications" element={<Notifications />} />
      </Route>
      <Route
        path="/officer"
        element={
          <RequireRole role="officer">
            <Layout />
          </RequireRole>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="jobs" element={<OfficerJobs />} />
        <Route path="jobs/:id" element={<JobPipeline />} />
        <Route path="applications/:id" element={<ApplicationDetail />} />
        <Route path="students" element={<Students />} />
        <Route path="companies" element={<Companies />} />
        <Route path="interviews" element={<Interviews />} />
      </Route>
      <Route path="*" element={<Home />} />
    </Routes>
  );
}
