import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { ErrorNote } from "../components/ui";

const BRANCHES = ["CSE", "IT", "ECE", "EE", "ME", "CE"];
const DEMO = import.meta.env.VITE_DEMO === "1"; // shows the fictional demo logins on the sign-in page

function AuthShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="auth-page">
      <section className="auth-hero" aria-hidden="true">
        <div className="logo big">P</div>
        <h2>PlaceRight</h2>
        <p>Campus placements in one place: eligible jobs, one-click applications, interview slots and offers, with every step recorded.</p>
        <ul className="hero-points">
          <li>Only jobs you are eligible for</li>
          <li>Live status of every application</li>
          <li>Interview times without clashes</li>
        </ul>
      </section>
      <main className="auth-card card" id="main">
        <h1>{title}</h1>
        {children}
      </main>
    </div>
  );
}

export function Login() {
  const { me, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (me) return <Navigate to={me.role === "officer" ? "/officer" : "/student"} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const who = await login(email, password);
      navigate(who.role === "officer" ? "/officer" : "/student");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Sign in">
      <form onSubmit={submit} className="stack">
        <label>
          College email
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Password
          <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <ErrorNote error={error} />
        <button type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="muted center">
        New student? <Link to="/register">Create your account</Link>
      </p>
      {DEMO && (
        <div className="demo-hint">
          <strong>Demo logins</strong> (fictional data, password <code>placeright-demo</code>):
          <br />
          Officer <code>officer@geu.ac.in</code> · Student <code>aarav.sharma@geu.ac.in</code>
        </div>
      )}
    </AuthShell>
  );
}

export function Register() {
  const { me, register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "", roll_no: "", branch: "CSE", graduation_year: "2028", skills: "" });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (me) return <Navigate to="/" replace />;
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register({
        ...form,
        graduation_year: Number(form.graduation_year),
        skills: form.skills
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      navigate("/student/profile");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Create your account">
      <form onSubmit={submit} className="stack">
        <label>
          Full name
          <input required minLength={2} autoComplete="name" value={form.name} onChange={set("name")} />
        </label>
        <label>
          College email
          <input type="email" required autoComplete="email" value={form.email} onChange={set("email")} aria-describedby="email-hint" />
          <span id="email-hint" className="hint">
            Use your @geu.ac.in address.
          </span>
        </label>
        <label>
          Password
          <input type="password" required minLength={8} maxLength={72} autoComplete="new-password" value={form.password} onChange={set("password")} aria-describedby="pw-hint" />
          <span id="pw-hint" className="hint">
            At least 8 characters.
          </span>
        </label>
        <div className="row2">
          <label>
            Roll number
            <input required pattern="[A-Za-z0-9-]+" value={form.roll_no} onChange={set("roll_no")} />
          </label>
          <label>
            Branch
            <select value={form.branch} onChange={set("branch")}>
              {BRANCHES.map((b) => (
                <option key={b}>{b}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="row2">
          <label>
            Graduation year
            <input type="number" min={2020} max={2035} required value={form.graduation_year} onChange={set("graduation_year")} />
          </label>
          <label>
            Skills
            <input placeholder="Python, SQL, React" value={form.skills} onChange={set("skills")} />
          </label>
        </div>
        <p className="hint">Your CGPA is added by the placement office from official results; until then you cannot apply.</p>
        <ErrorNote error={error} />
        <button type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </button>
      </form>
      <p className="muted center">
        Already registered? <Link to="/login">Sign in</Link>
      </p>
    </AuthShell>
  );
}
