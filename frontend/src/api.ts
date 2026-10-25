// Thin client for the PlaceRight API. Every call goes to /api/... (forwarded to the backend), carries the signed-in
// user's token, and turns error responses into ApiError with the server's message.

export type Role = "officer" | "student";
export type Status = "applied" | "shortlisted" | "interview" | "offered" | "rejected" | "withdrawn";

export interface Me {
  user_id: number | null;
  email: string | null;
  role: Role;
  student_id: number | null;
  name: string | null;
}
export interface Student {
  id: number;
  name: string;
  email: string;
  roll_no: string;
  branch: string;
  cgpa: number | null;
  graduation_year: number;
  skills: string[];
  resume_name: string | null;
  resume_uploaded_at: string | null;
}
export interface Company {
  id: number;
  name: string;
  website: string | null;
  industry: string;
  open_jobs: number;
}
export interface Job {
  id: number;
  company_id: number;
  company_name: string | null;
  title: string;
  description: string;
  location: string;
  ctc_lpa: number | null;
  min_cgpa: number;
  eligible_branches: string[];
  openings: number;
  deadline: string;
  status: "open" | "closed";
  applications: number | null;
}
export interface Application {
  id: number;
  student_id: number;
  job_id: number;
  status: Status;
  created_at: string;
  updated_at: string;
  student_name?: string | null;
  student_email?: string | null;
  roll_no?: string | null;
  branch?: string | null;
  cgpa?: number | null;
  job_title?: string | null;
  company_name?: string | null;
  interview_at?: string | null;
}
export interface Event {
  from_status: string | null;
  to_status: string;
  actor: string;
  at: string;
}
export interface Interview {
  id: number;
  application_id: number;
  student_id: number;
  starts_at: string;
  ends_at: string;
  mode: "online" | "onsite";
  location: string;
  panel: string;
  student_name?: string | null;
  job_title?: string | null;
  company_name?: string | null;
}
export interface Notification {
  id: number;
  kind: string;
  message: string;
  application_id: number | null;
  created_at: string;
  read_at: string | null;
}
export interface Overview {
  students: number;
  students_unverified: number;
  open_jobs: number;
  applications: number;
  offers: number;
  placed_students: number;
  placement_rate: number;
  status_funnel: Partial<Record<Status, number>>;
  applications_per_job: { job_id: number; title: string; company_name: string; applications: number; offers: number }[];
  branch_placements: { branch: string; students: number; placed: number }[];
  upcoming_interviews: number;
}
export interface JobStats {
  job_id: number;
  openings: number;
  total_applications: number;
  by_status: Partial<Record<Status, number>>;
  offers_left: number;
}
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
export interface Workflow {
  transitions: Record<Status, Status[]>;
  branches: string[];
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";
const TOKEN_KEY = "placeright.token";

// sessionStorage: the token is gone when the tab closes. See README "Limitations" for the trade-off vs cookies.
export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (t: string) => sessionStorage.setItem(TOKEN_KEY, t),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

async function raw(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const res = await fetch(BASE + path, { ...init, headers });
  if (!res.ok) {
    let msg = res.statusText || "Request failed";
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
      else if (Array.isArray(body.detail)) msg = body.detail.map((d: { msg: string }) => d.msg).join("; "); // 422 details
    } catch {
      /* not JSON */
    }
    if (res.status === 401 && token) onUnauthorized?.(); // expired session: back to the login page
    throw new ApiError(res.status, msg);
  }
  return res;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await raw(path, init);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

// A fresh key per user action; a retry of the SAME action reuses it, so the server applies it once.
export const newIdempotencyKey = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;

const post = (body: unknown, extra: HeadersInit = {}): RequestInit => ({ method: "POST", body: JSON.stringify(body), headers: extra });

export const api = {
  // auth
  login: (email: string, password: string) =>
    json<{ access_token: string; me: Me }>("/auth/login", post({ email, password })),
  register: (body: Record<string, unknown>) => json<{ access_token: string; me: Me }>("/auth/register", post(body)),
  me: () => json<Me>("/auth/me"),
  workflow: () => json<Workflow>("/meta/workflow"),

  // students
  student: (id: number) => json<Student>(`/students/${id}`),
  updateStudent: (id: number, body: Partial<Pick<Student, "name" | "skills" | "cgpa">>) =>
    json<Student>(`/students/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  students: (params: Record<string, string | number | boolean | undefined>) => json<Page<Student>>(`/students?${qs(params)}`),
  eligibleJobs: (id: number) => json<Job[]>(`/students/${id}/eligible-jobs`),
  uploadResume: (id: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return json<Student>(`/students/${id}/resume`, { method: "PUT", body: fd });
  },
  resumeBlob: async (id: number) => (await raw(`/students/${id}/resume`)).blob(),

  // companies & jobs
  companies: () => json<Company[]>("/companies"),
  createCompany: (body: Partial<Company>) => json<Company>("/companies", post(body)),
  jobs: (params: Record<string, string | number | undefined>) => json<Page<Job>>(`/jobs?${qs(params)}`),
  job: (id: number) => json<Job>(`/jobs/${id}`),
  createJob: (body: Record<string, unknown>) => json<Job>("/jobs", post(body)),
  closeJob: (id: number) => json<Job>(`/jobs/${id}/close`, { method: "POST" }),
  jobStats: (id: number) => json<JobStats>(`/jobs/${id}/stats`),
  applicantsCsv: async (id: number) => (await raw(`/jobs/${id}/applicants.csv`)).blob(),

  // applications
  apply: (studentId: number, jobId: number, key: string) =>
    json<Application>("/applications", post({ student_id: studentId, job_id: jobId }, { "Idempotency-Key": key })),
  applications: (params: Record<string, string | number | undefined>) => json<Application[]>(`/applications?${qs(params)}`),
  application: (id: number) => json<Application>(`/applications/${id}`),
  setStatus: (id: number, status: Status, key: string) =>
    json<Application>(`/applications/${id}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
      headers: { "Idempotency-Key": key },
    }),
  history: (id: number) => json<Event[]>(`/applications/${id}/history`),

  // interviews
  interview: (appId: number) => json<Interview>(`/applications/${appId}/interview`),
  schedule: (appId: number, body: Record<string, unknown>) =>
    json<Interview>(`/applications/${appId}/interview`, { method: "PUT", body: JSON.stringify(body) }),
  cancelInterview: (appId: number) => json<void>(`/applications/${appId}/interview`, { method: "DELETE" }),
  interviews: () => json<Interview[]>("/interviews"),

  // notifications & dashboard
  notifications: () => json<{ items: Notification[]; unread: number }>("/notifications"),
  readNotification: (id: number) => json<void>(`/notifications/${id}/read`, { method: "POST" }),
  readAll: () => json<{ marked: number }>("/notifications/read-all", { method: "POST" }),
  overview: () => json<Overview>("/stats/overview"),
};

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "" && v !== false) p.set(k, String(v));
  return p.toString();
}

/** Saves a Blob as a file (CSV export, resume download). */
export function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
