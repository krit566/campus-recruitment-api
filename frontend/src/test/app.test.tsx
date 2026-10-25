import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ineligibility } from "../pages/student/Jobs";
import { app, axeViolations, fakeApi, JOB, OFFICER, renderApp, STUDENT, STUDENT_ROW, WORKFLOW } from "./helpers";

const OVERVIEW = {
  students: 40,
  students_unverified: 3,
  open_jobs: 10,
  applications: 53,
  offers: 6,
  placed_students: 6,
  placement_rate: 0.15,
  status_funnel: { applied: 20, shortlisted: 8, interview: 8, offered: 6, rejected: 10, withdrawn: 1 },
  applications_per_job: [{ job_id: 3, title: "Software Engineer Intern", company_name: "Northwind Payments", applications: 12, offers: 2 }],
  branch_placements: [{ branch: "CSE", students: 14, placed: 2 }],
  upcoming_interviews: 8,
};

describe("sign in", () => {
  it("signs an officer in, stores the token and opens the dashboard", async () => {
    const calls = fakeApi({
      "POST /auth/login": { access_token: "tok-officer", me: OFFICER },
      "GET /stats/overview": OVERVIEW,
    });
    const { container } = renderApp("/login");
    expect(await axeViolations(container)).toEqual([]);
    await userEvent.type(screen.getByLabelText("College email"), "officer@geu.ac.in");
    await userEvent.type(screen.getByLabelText("Password"), "secret-pass");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Placement dashboard" })).toBeInTheDocument();
    expect(sessionStorage.getItem("placeright.token")).toBe("tok-officer");
    expect(calls[0].body).toEqual({ email: "officer@geu.ac.in", password: "secret-pass" });
    expect(screen.getByText("15%")).toBeInTheDocument(); // placement rate shown as a percentage
  });

  it("shows the server's message when the password is wrong", async () => {
    fakeApi({ "POST /auth/login": () => ({ status: 401, body: { detail: "wrong email or password" } }) });
    renderApp("/login");
    await userEvent.type(screen.getByLabelText("College email"), "x@geu.ac.in");
    await userEvent.type(screen.getByLabelText("Password"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("wrong email or password");
    expect(sessionStorage.getItem("placeright.token")).toBeNull();
  });

  it("sends a student who opens an officer page to their own home", async () => {
    fakeApi({
      "GET /auth/me": STUDENT,
      "GET /students/7": STUDENT_ROW,
      "GET /applications": [],
      "GET /interviews": [],
      "GET /notifications": { items: [], unread: 0 },
      "GET /students/7/eligible-jobs": [JOB],
    });
    renderApp("/officer", "tok-student");
    expect(await screen.findByRole("heading", { name: "Hi, Asha" })).toBeInTheDocument();
  });

  it("drops an expired session and returns to sign-in", async () => {
    fakeApi({ "GET /auth/me": () => ({ status: 401, body: { detail: "your session has expired; please sign in again" } }) });
    renderApp("/student", "old-token");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(sessionStorage.getItem("placeright.token")).toBeNull();
  });
});

describe("student", () => {
  it("explains why a job is not open to them", () => {
    expect(ineligibility(JOB as never, { ...STUDENT_ROW, branch: "ME" } as never)).toBe("Open to CSE, IT only");
    expect(ineligibility(JOB as never, { ...STUDENT_ROW, cgpa: null } as never)).toBe("Needs your verified CGPA");
    expect(ineligibility(JOB as never, { ...STUDENT_ROW, cgpa: 7.0 } as never)).toBe("Needs CGPA 7.5+");
    expect(ineligibility(JOB as never, STUDENT_ROW as never)).toBe("");
  });

  it("lists only eligible jobs by default and passes an accessibility check", async () => {
    fakeApi({
      "GET /auth/me": STUDENT,
      "GET /students/7": STUDENT_ROW,
      "GET /jobs": { items: [JOB, { ...JOB, id: 4, title: "Embedded Engineer", eligible_branches: ["ECE"] }], total: 2, limit: 100, offset: 0 },
      "GET /applications": [],
      "GET /notifications": { items: [], unread: 0 },
    });
    const { container } = renderApp("/student/jobs", "tok");
    expect(await screen.findByText("1 of 2 open jobs match your branch and CGPA.")).toBeInTheDocument();
    expect(screen.queryByText("Embedded Engineer")).toBeNull();
    await userEvent.click(screen.getByLabelText("Show jobs I am not eligible for"));
    expect(screen.getByText("Embedded Engineer")).toBeInTheDocument();
    expect(screen.getByText("Open to ECE only")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });

  it("applies with an Idempotency-Key and reuses it when retrying after a network failure", async () => {
    let attempts = 0;
    const calls = fakeApi({
      "GET /auth/me": STUDENT,
      "GET /jobs/3": JOB,
      "GET /students/7": STUDENT_ROW,
      "GET /applications": [],
      "GET /notifications": { items: [], unread: 0 },
      "POST /applications": () => {
        attempts += 1;
        // first attempt: the server is unreachable (e.g. a timeout); second attempt succeeds
        return attempts === 1 ? { status: 503, body: { detail: "service unavailable, try again" } } : { status: 201, body: app(9, "applied", "Asha Rawat") };
      },
    });
    renderApp("/student/jobs/3", "tok");
    const button = await screen.findByRole("button", { name: "Apply now" });
    await userEvent.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent("try again");
    await userEvent.click(screen.getByRole("button", { name: "Apply now" }));
    expect(await screen.findByText("Track it")).toBeInTheDocument();
    const posts = calls.filter((c) => c.method === "POST" && c.path === "/applications");
    expect(posts).toHaveLength(2);
    const k1 = posts[0].headers.get("Idempotency-Key");
    expect(k1).toBeTruthy();
    expect(posts[1].headers.get("Idempotency-Key")).toBe(k1); // same action, same key: the server applies it once
  });
});

describe("officer pipeline", () => {
  const pipelineApi = (onPatch: (body: unknown) => { status?: number; body?: unknown }) =>
    fakeApi({
      "GET /auth/me": OFFICER,
      "GET /jobs/3": JOB,
      "GET /jobs/3/stats": { job_id: 3, openings: 2, total_applications: 3, by_status: { applied: 1, interview: 1, rejected: 1 }, offers_left: 2 },
      "GET /applications": [app(1, "applied", "Rohan Chauhan"), app(2, "interview", "Meera Singh"), app(3, "rejected", "Yash Negi")],
      "GET /meta/workflow": WORKFLOW,
      "PATCH /applications/2/status": ({ body }) => onPatch(body),
    });

  it("offers only the moves the workflow allows, forward moves first", async () => {
    pipelineApi(() => ({}));
    const { container } = renderApp("/officer/jobs/3", "tok");
    const applied = await screen.findByRole("region", { name: /Applied/ });
    expect(within(applied).getAllByRole("button").map((b) => b.textContent)).toEqual(["Shortlist", "Reject"]);
    const interview = screen.getByRole("region", { name: /Interview/ });
    expect(within(interview).getAllByRole("button").map((b) => b.textContent)).toEqual(["Make offer", "Reject"]);
    const closed = screen.getByRole("region", { name: /Closed/ });
    expect(within(closed).queryAllByRole("button")).toHaveLength(0); // final states cannot move
    expect(await axeViolations(container)).toEqual([]);
  });

  it("sends the move with an Idempotency-Key and shows the server's refusal", async () => {
    const seen: unknown[] = [];
    const calls = pipelineApi((body) => {
      seen.push(body);
      return { status: 409, body: { detail: "all openings for this job already have offers" } };
    });
    renderApp("/officer/jobs/3", "tok");
    await userEvent.click(await screen.findByRole("button", { name: "Make offer: Meera Singh" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("all openings for this job already have offers");
    expect(seen).toEqual([{ status: "offered" }]);
    const patch = calls.find((c) => c.method === "PATCH")!;
    expect(patch.headers.get("Idempotency-Key")).toBeTruthy();
    expect(patch.headers.get("Authorization")).toBe("Bearer tok");
  });

  it("asks before rejecting", async () => {
    const calls = pipelineApi(() => ({}));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderApp("/officer/jobs/3", "tok");
    await userEvent.click(await screen.findByRole("button", { name: "Reject: Meera Singh" }));
    expect(confirm).toHaveBeenCalled();
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(false));
  });

  it("dashboard passes an accessibility check", async () => {
    fakeApi({ "GET /auth/me": OFFICER, "GET /stats/overview": OVERVIEW });
    const { container } = renderApp("/officer", "tok");
    expect(await screen.findByText("Placements by branch")).toBeInTheDocument();
    expect(await axeViolations(container)).toEqual([]);
  });
});
