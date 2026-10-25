import { render } from "@testing-library/react";
import axe from "axe-core";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../auth";

export type Handler = (req: { method: string; path: string; headers: Headers; body: unknown }) => { status?: number; body?: unknown };

/** Replaces fetch with a tiny fake API. `routes` maps "METHOD /path" (query string ignored) to a handler or a body. */
export function fakeApi(routes: Record<string, Handler | object>) {
  const calls: { method: string; path: string; headers: Headers; body: unknown }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input), "http://localhost");
    const path = url.pathname.replace(/^\/api/, "");
    const method = (init.method ?? "GET").toUpperCase();
    const headers = new Headers(init.headers);
    const body = typeof init.body === "string" ? JSON.parse(init.body) : init.body;
    const req = { method, path, headers, body };
    calls.push(req);
    const route = routes[`${method} ${path}`];
    if (!route) return new Response(JSON.stringify({ detail: `no fake for ${method} ${path}` }), { status: 404 });
    const out = typeof route === "function" ? (route as Handler)(req) : { body: route };
    return new Response(out.status === 204 ? null : JSON.stringify(out.body ?? {}), {
      status: out.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

export function renderApp(path: string, token?: string) {
  if (token) sessionStorage.setItem("placeright.token", token);
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

export async function axeViolations(container: HTMLElement) {
  // colour contrast needs real layout and fonts, so it is checked in the browser (Lighthouse), not in jsdom
  const res = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  return res.violations.map((v) => `${v.id}: ${v.nodes.length} node(s)`);
}

export const OFFICER = { user_id: 1, email: "officer@geu.ac.in", role: "officer", student_id: null, name: null };
export const STUDENT = { user_id: 2, email: "asha@geu.ac.in", role: "student", student_id: 7, name: "Asha Rawat" };
export const STUDENT_ROW = {
  id: 7,
  name: "Asha Rawat",
  email: "asha@geu.ac.in",
  roll_no: "GE-CSE-24007",
  branch: "CSE",
  cgpa: 8.1,
  graduation_year: 2028,
  skills: ["Python"],
  resume_name: null,
  resume_uploaded_at: null,
};
export const JOB = {
  id: 3,
  company_id: 1,
  company_name: "Northwind Payments",
  title: "Software Engineer Intern",
  description: "Build payment APIs.",
  location: "Bengaluru",
  ctc_lpa: 12,
  min_cgpa: 7.5,
  eligible_branches: ["CSE", "IT"],
  openings: 2,
  deadline: "2099-01-01",
  status: "open",
  applications: 4,
};
export const WORKFLOW = {
  transitions: {
    applied: ["rejected", "shortlisted", "withdrawn"],
    shortlisted: ["interview", "rejected", "withdrawn"],
    interview: ["offered", "rejected"],
    offered: [],
    rejected: [],
    withdrawn: [],
  },
  branches: ["CSE", "IT", "ECE", "EE", "ME", "CE"],
};
export const app = (id: number, status: string, name: string) => ({
  id,
  student_id: id + 100,
  job_id: 3,
  status,
  created_at: "2026-10-10T10:00:00Z",
  updated_at: "2026-10-12T10:00:00Z",
  student_name: name,
  roll_no: `GE-CSE-24${id}`,
  branch: "CSE",
  cgpa: 8.2,
  job_title: "Software Engineer Intern",
  company_name: "Northwind Payments",
  interview_at: null,
});
