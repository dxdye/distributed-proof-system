// Typed client for the coordination API (dpc/api/app.py).
import { accessToken } from "./auth";

export type GlossaryEntry = { name: string; type: string };
export type Component = {
  target: "type" | "value" | "ctor";
  label: string;
  text: string;
  glossary: GlossaryEntry[];
  // Rendered without the submission's own display rules (ADR 0011).
  trusted_text?: string | null;
  trusted_glossary?: GlossaryEntry[];
};
export type UnitView = {
  declaration: string;
  decl_kind: string;
  components: Component[];
  context: string[];
};
export type Question = { id: string; text: string };
export type Lease = {
  lease_id: string;
  duty: "review" | "pvv" | "claim";
  status: string;
  extendable: boolean;
  expected_minutes: number;
  min_reason_chars: number;
  ticket: {
    ticket_id: string;
    paper: string;
    repo_url: string;
    commit: string;
    domain: string;
    view: UnitView;
    questions: Question[];
  };
  claim?: {
    claim_id: string;
    reason: string;
    failed?: string[];
    evidence: { kind: string; file_sha256: string } | null;
  };
};
export type Card = {
  ticket_id: string;
  declaration: string;
  decl_kind: string;
  domain: string;
  paper: string;
  expected_minutes: number;
};
export type ChoiceSet = { set_id: string | null; tickets: Card[] };
export type HistoryItem = {
  declaration: string;
  paper: string;
  verdict: "correct" | "incorrect";
  duty: string;
  submitted: string;
  outcome: string | null;
  planted_error: boolean | null;
};
export type Me = {
  reviewer_id: string;
  pseudonym: string;
  group: string;
  maintainer: boolean;
  roles: Record<string, string[]>;
  reliability: number;
  wip_limit: number;
  leases: Lease[];
  history: HistoryItem[];
};
export type Stats = {
  reviewers: number;
  reviewers_by_group: Record<string, number>;
  submissions: number;
  tickets_by_status: Record<string, number>;
  reviews_last_7_days: number;
  open_claims: number;
  active_leases: number;
  audit_head: string | null;
};
export type ReviewInput = {
  verdict: "correct" | "incorrect";
  reason: string;
  failed: string[];
  evidence?: string | null;
  evidence_kind?: string | null;
  ai_used: boolean;
  ai_provider?: string | null;
};
export type SubmissionRow = {
  submission_id: string;
  title: string;
  repo_url: string;
  commit: string;
  closed: boolean;
  tickets: Record<string, number>;
};
export type Escalated = {
  ticket_id: string;
  declaration: string;
  paper: string;
  votes: { verdict: string; reason: string }[];
};

export type Session = {
  authenticated: boolean;
  provider?: string;
  registered?: boolean;
  error?: string;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  const token = await accessToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  if (!res.ok) {
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      detail = typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
    } catch {
      /* plain text */
    }
    throw new ApiError(res.status, detail || res.statusText);
  }
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("application/json") ? JSON.parse(text) : text) as T;
}

export const api = {
  session: () => request<Session>("GET", "/api/auth/session"),
  notice: () => request<{ version: string; text: string }>("GET", "/api/notice"),
  register: (body: {
    pseudonym: string;
    group: string;
    affiliations: string[];
    notice_acknowledged: boolean;
  }) => request<{ reviewer_id: string; token?: string }>("POST", "/api/register", body),
  me: () => request<Me>("GET", "/api/me"),
  declareAffiliation: (lab: string) => request("POST", "/api/me/affiliations", { lab }),
  choiceSet: () => request<ChoiceSet>("POST", "/api/choice-set"),
  take: (set_id: string, ticket_id: string) =>
    request<Lease>("POST", "/api/leases", { set_id, ticket_id }),
  lease: (id: string) => request<Lease>("GET", `/api/leases/${id}`),
  extend: (id: string) => request<Lease>("POST", `/api/leases/${id}/extend`),
  giveBack: (id: string) => request("POST", `/api/leases/${id}/return`),
  review: (id: string, body: ReviewInput) => request("POST", `/api/leases/${id}/review`, body),
  decideClaim: (id: string, confirmed: boolean, reason: string) =>
    request("POST", `/api/leases/${id}/claim`, { confirmed, reason }),
  nextDuty: () => request<Lease | null>("POST", "/api/duties/next"),
  blob: (sha: string) => request<string>("GET", `/api/blobs/${sha}`),
  stats: () => request<Stats>("GET", "/api/stats"),
  attention: () => request<Record<string, number>>("GET", "/api/attention"),
  admin: {
    tick: () => request<{ expired: number; revealed: number }>("POST", "/api/admin/tick"),
    submissions: () => request<SubmissionRow[]>("GET", "/api/admin/submissions"),
    escalated: () => request<Escalated[]>("GET", "/api/admin/escalated"),
    decide: (ticket: string, error: boolean, reason: string) =>
      request("POST", `/api/admin/tickets/${ticket}/decide`, { error, reason }),
    close: (submission: string) => request("POST", `/api/admin/submissions/${submission}/close`),
  },
};
