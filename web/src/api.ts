// Typed client for the coordination API (dpc/api/app.py).
import { accessToken } from "./auth";

export type GlossaryEntry = {
  name: string;
  type: string;
  origin?: "core" | "library" | "submission" | null;
  doc?: string | null;
  note?: string | null;
};
export type Component = {
  target: "type" | "value" | "ctor";
  label: string;
  text: string;
  glossary: GlossaryEntry[];
  // Rendered without the submission's own display rules (ADR 0011).
  trusted_text?: string | null;
  trusted_glossary?: GlossaryEntry[];
  // The same term typeset as LaTeX, where unambiguous (null: not available).
  latex?: string | null;
};
export type UnitView = {
  declaration: string;
  decl_kind: string;
  components: Component[];
  context: string[];
};
export type Question = { id: string; text: string };
export type PaperPassage = {
  source: {
    title: string;
    arxiv: string | null;
    version: string | null;
    url: string | null;
  };
  locator: string;
  statement: string;
  mapped_by: string;
  note: string;
};
export type Lease = {
  lease_id: string;
  duty: "review" | "pvv" | "claim";
  status: string;
  extendable: boolean;
  expected_minutes: number | null;
  min_reason_chars: number;
  ticket: {
    ticket_id: string;
    paper: string;
    repo_url: string;
    commit: string;
    domain: string;
    tier?: string;
    view: UnitView;
    questions: Question[];
    purpose?: string;
    paper_ref: string | null;
    paper_passage: PaperPassage | null;
    mapping_contested_by_me: boolean;
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
  tier: string;
  paper: string;
  expected_minutes: number | null;
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
  pvv_waiting: number; // re-checks next_duty could hand out now
  preferences: { domains: string[]; tiers: string[] };
  tiers_open: string[];
  leases: Lease[];
  history: HistoryItem[];
};
export type Stats = {
  reviewers: number;
  reviewers_by_group: Record<string, number>;
  submissions: number;
  planted_errors_revealed: number;
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
export type ThreadSummary = {
  submission_id: string;
  declaration: string;
  decl_kind: string;
  paper: string;
  domain: string;
  outcome: string;
  posts: number;
  last_activity: string;
  can_share: boolean;
  score: number; // worth reading: sorts the list, says nothing about the decision
  my_vote: number;
};
export type Post = {
  post_id: string;
  kind: "review" | "comment";
  author: string;
  is_me: boolean;
  maintainer: boolean;
  member_since: string;
  reviewed_here: boolean;
  at: string;
  score: number;
  my_vote: number;
  ai_used: boolean;
  hidden: string | null;
  reported_by_me?: boolean;
  text: string;
  verdict?: "correct" | "incorrect";
  reason?: string;
  failed?: string[];
};
export type Thread = {
  submission_id: string;
  declaration: string;
  decl_kind: string;
  paper: string;
  repo_url: string;
  commit: string;
  domain: string;
  outcome: string;
  decided_at: string | null;
  view: UnitView;
  paper_passage: PaperPassage | null;
  me: {
    label: string | null;
    named: boolean;
    can_share: boolean;
    reviewed_here: boolean;
  };
  reopen_pending: boolean;
  score: number;
  my_vote: number;
  posts: Post[];
};
// The public progress page (proposal C-26): counts are by declaration, never
// by ticket; no verdict tallies of open work.
export type ProgressSummary = {
  submission_id: string;
  title: string;
  repo_url: string;
  commit: string;
  paper_ref: string | null;
  paper_url: string | null;
  opened: string;
  closed: boolean;
  prl: number;
  prl_meaning: string;
  declarations: number;
  decided: number;
  accepted: number;
  errors: number;
  in_review: number;
  not_started: number;
  coverage: number;
  residual_error: number | null;
  forecast: { p50_weeks: number; p85_weeks: number } | null;
  interest: number | null;
  main_statement: string | null;
  main_locator: string | null;
};
export type ProgressUnit = {
  declaration: string;
  decl_kind: string;
  tier: string;
  domain: string;
  state: "accepted" | "error" | "in review" | "not started";
  discussion: boolean;
};
export type ProgressDetail = ProgressSummary & {
  root: string | null;
  main_view: UnitView | null;
  units: ProgressUnit[];
  timeline: { at: string; decided: number }[];
  notes: Post[];
  basis: Basis | null;
  // null: hidden while a planted error of the submission is unrevealed
  library_definitions: LibraryDefinition[] | null;
};
// What a result relies on (proposal C-29).
export type Basis = {
  toolchain: string;
  axioms: string[];
  libraries: { name: string; url: string; rev: string }[];
  hardened_files: number | null;
  hardened_unchanged: boolean | null;
  replayed: boolean;
  modules_replayed: number;
  constants_replayed: number;
  replay_failures: number;
  modules_trusted: number;
  modules_core: number;
  libraries_replayed: boolean;
  second_kernel: boolean;
};
export type LibraryDefinition = {
  name: string;
  type: string;
  origin: "library" | "core";
  doc: string | null;
  note: string | null;
  used_by: string[];
  reviewed: boolean;
};
export type MaintainerDeclaration = {
  submission_id: string;
  declaration: string;
  decl_kind: string;
  tier: string;
  domain: string;
  state: ProgressUnit["state"];
  decided_at: string | null;
  paper: string;
  repo_url: string;
  commit: string;
  paper_ref: string | null;
  paper_passage: PaperPassage | null;
  view: UnitView;
  questions: Question[];
  purpose: string;
  contested: number;
  discussion: boolean;
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
  setPreferences: (domains: string[], tiers: string[]) =>
    request("PUT", "/api/me/preferences", { domains, tiers }),
  domains: () => request<string[]>("GET", "/api/domains"),
  choiceSet: () => request<ChoiceSet>("POST", "/api/choice-set"),
  take: (set_id: string, ticket_id: string) =>
    request<Lease>("POST", "/api/leases", { set_id, ticket_id }),
  lease: (id: string) => request<Lease>("GET", `/api/leases/${id}`),
  extend: (id: string) => request<Lease>("POST", `/api/leases/${id}/extend`),
  giveBack: (id: string) => request("POST", `/api/leases/${id}/return`),
  review: (id: string, body: ReviewInput) => request("POST", `/api/leases/${id}/review`, body),
  contestMapping: (id: string, reason: string) =>
    request("POST", `/api/leases/${id}/contest-mapping`, { reason }),
  decideClaim: (id: string, confirmed: boolean, reason: string) =>
    request("POST", `/api/leases/${id}/claim`, { confirmed, reason }),
  nextDuty: () => request<Lease | null>("POST", "/api/duties/next"),
  blob: (sha: string) => request<string>("GET", `/api/blobs/${sha}`),
  discussions: () => request<ThreadSummary[]>("GET", "/api/discussions"),
  thread: (sid: string, decl: string) =>
    request<Thread>(
      "GET",
      `/api/thread?submission_id=${encodeURIComponent(sid)}&declaration=${encodeURIComponent(decl)}`,
    ),
  post: (
    sid: string,
    decl: string,
    text: string,
    showPseudonym: boolean,
    aiProvider: string | null,
  ) =>
    request("POST", "/api/thread/posts", {
      submission_id: sid,
      declaration: decl,
      text,
      show_pseudonym: showPseudonym,
      ai_used: aiProvider !== null,
      ai_provider: aiProvider,
    }),
  share: (sid: string, decl: string, showPseudonym: boolean) =>
    request("POST", "/api/thread/share", {
      submission_id: sid,
      declaration: decl,
      show_pseudonym: showPseudonym,
    }),
  requestReopen: (sid: string, decl: string, reason: string) =>
    request("POST", "/api/thread/reopen", {
      submission_id: sid,
      declaration: decl,
      reason,
    }),
  vote: (postId: string, value: number) => request("POST", `/api/posts/${postId}/vote`, { value }),
  voteThread: (sid: string, decl: string, value: number) =>
    request("POST", "/api/thread/vote", { submission_id: sid, declaration: decl, value }),
  withdrawReport: (postId: string) => request("DELETE", `/api/posts/${postId}/report`),
  report: (postId: string, reason: string) =>
    request("POST", `/api/posts/${postId}/report`, { reason }),
  progress: () => request<ProgressSummary[]>("GET", "/api/progress"),
  progressDetail: (sid: string) =>
    request<ProgressDetail>("GET", `/api/progress/${encodeURIComponent(sid)}`),
  note: (sid: string, text: string, showPseudonym: boolean) =>
    request<{ post_id: string }>("POST", `/api/progress/${encodeURIComponent(sid)}/notes`, {
      text,
      show_pseudonym: showPseudonym,
    }),
  stats: () => request<Stats>("GET", "/api/stats"),
  attention: () => request<Record<string, number>>("GET", "/api/attention"),
  admin: {
    tick: () => request<{ expired: number; revealed: number }>("POST", "/api/admin/tick"),
    submissions: () => request<SubmissionRow[]>("GET", "/api/admin/submissions"),
    escalated: () => request<Escalated[]>("GET", "/api/admin/escalated"),
    declaration: (sid: string, decl: string) =>
      request<MaintainerDeclaration>(
        "GET",
        `/api/admin/declaration?submission_id=${encodeURIComponent(sid)}&declaration=${encodeURIComponent(decl)}`,
      ),
    contested: () =>
      request<
        {
          ticket_id: string;
          declaration: string;
          paper: string;
          locator: string;
          reasons: string[];
        }[]
      >("GET", "/api/admin/contested"),
    decide: (ticket: string, error: boolean, reason: string) =>
      request("POST", `/api/admin/tickets/${ticket}/decide`, { error, reason }),
    close: (submission: string) => request("POST", `/api/admin/submissions/${submission}/close`),
    reports: () =>
      request<
        {
          post_id: string;
          submission_id: string;
          declaration: string;
          text: string;
          kind: string;
          reasons: string[];
        }[]
      >("GET", "/api/admin/reports"),
    hide: (postId: string, reason: string) =>
      request("POST", `/api/admin/posts/${postId}/hide`, { reason }),
    reopens: () =>
      request<
        {
          request_id: string;
          ticket_id: string;
          declaration: string;
          paper: string;
          submission_id: string;
          outcome: string;
          reason: string;
        }[]
      >("GET", "/api/admin/reopens"),
    resolveReopen: (id: string, reopen: boolean, reason: string) =>
      request("POST", `/api/admin/reopens/${id}`, { reopen, reason }),
  },
};
