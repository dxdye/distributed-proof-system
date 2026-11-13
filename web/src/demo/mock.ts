// Click dummy: a simulated backend in the browser (build mode "demo").
//
// The web client is the real one; this module answers its /api/* requests from
// a snapshot exported from the current implementation (`dpc export-demo`):
// ticket views, tiers, paper passages, questions. The rules are simplified:
// verdicts are recorded, planted errors are revealed right after the verdict
// (the real system reveals them days later, in batches), and the decision
// rule is not run. Nothing leaves the browser; the state lives in session
// storage and can be reset.
import snapshotJson from "../../demo/snapshot.json";

type Json = Record<string, unknown>;
type Tier = "easy" | "medium" | "hard" | "excellence";
export type Role = "newcomer" | "pv" | "pvv" | "maintainer";

type SnapTicket = {
  ticket_id: string;
  declaration: string;
  decl_kind: string;
  domain: string;
  tier: Tier;
  view: Json;
  paper: Json | null;
  honeypot: { operator: string; original: string; mutant: string } | null;
};
type SnapSubmission = {
  submission_id: string;
  title: string;
  repo_url: string;
  commit: string;
  paper_ref: string | null;
  tickets: SnapTicket[];
};
type Snapshot = {
  notice: { version: string; text: string };
  questions: Record<string, { id: string; text: string }[]>;
  purpose: Record<string, string>;
  min_reason_chars: number;
  choice_set_size: number;
  submissions: SnapSubmission[];
};
const snap = snapshotJson as unknown as Snapshot;

type HistoryItem = {
  declaration: string;
  paper: string;
  verdict: "correct" | "incorrect";
  duty: string;
  submitted: string;
  outcome: string | null;
  planted_error: boolean | null;
};
type Lease = {
  lease_id: string;
  role: Role;
  ticket_id: string;
  duty: "review" | "claim";
  claim_id: string | null;
  status: "active" | "done" | "returned";
  extended: boolean;
};
type Claim = {
  claim_id: string;
  ticket_id: string;
  by: Role | "other";
  reason: string;
  failed: string[];
  status: "open" | "confirmed" | "rejected";
};
type Person = {
  prefs: { domains: string[]; tiers: string[] };
  set: { set_id: string; tickets: string[] } | null;
  history: HistoryItem[];
  seen: string[]; // ticket ids worked on (never offered again)
};
type State = {
  version: number;
  leases: Record<string, Lease>;
  claims: Claim[];
  contests: Record<string, string[]>;
  status: Record<string, string>; // ticket id -> open | accepted | error | escalate
  revealed: string[];
  closed: string[];
  people: Record<Role, Person>;
  next: number;
};

export const ROLES: { role: Role; label: string; hint: string }[] = [
  {
    role: "newcomer",
    label: "Newcomer",
    hint: "New account: easy and medium tickets, no weight yet.",
  },
  { role: "pv", label: "Reviewer (PV)", hint: "Earned trust in the domains: hard tickets open." },
  { role: "pvv", label: "Re-checker (PVV)", hint: "Re-checks verdicts and decides claims." },
  { role: "maintainer", label: "Maintainer", hint: "Escalations, contested mappings, closing." },
];
const PROFILE: Record<
  Role,
  {
    pseudonym: string;
    group: string;
    tiers: Tier[];
    wip: number;
    roles: string[];
    maintainer: boolean;
  }
> = {
  newcomer: {
    pseudonym: "demo-newcomer",
    group: "student",
    tiers: ["easy", "medium"],
    wip: 1,
    roles: [],
    maintainer: false,
  },
  pv: {
    pseudonym: "demo-reviewer",
    group: "doctoral",
    tiers: ["easy", "medium", "hard"],
    wip: 2,
    roles: ["PV"],
    maintainer: false,
  },
  pvv: {
    pseudonym: "demo-rechecker",
    group: "expert",
    tiers: ["easy", "medium", "hard", "excellence"],
    wip: 3,
    roles: ["PV", "PVV"],
    maintainer: false,
  },
  maintainer: {
    pseudonym: "demo-maintainer",
    group: "expert",
    tiers: ["easy", "medium", "hard", "excellence"],
    wip: 3,
    roles: ["PV", "PVV", "maintainer"],
    maintainer: true,
  },
};

const kindOf = (declKind: string) =>
  declKind === "theorem" ? "theorem" : declKind === "inductive" ? "structure" : "definition";

const KEY = "dpc.demo.state";
const TOKEN = "dpc.token";
const tickets = new Map<string, { t: SnapTicket; sub: SnapSubmission }>();
for (const sub of snap.submissions)
  for (const t of sub.tickets) tickets.set(t.ticket_id, { t, sub });

function find(decl: string, honeypot: boolean): string | undefined {
  for (const [id, { t }] of tickets)
    if (t.declaration === decl && !!t.honeypot === honeypot) return id;
  return undefined;
}

function fresh(): State {
  const person = (): Person => ({
    prefs: { domains: [], tiers: [] },
    set: null,
    history: [],
    seen: [],
  });
  const s: State = {
    version: 1,
    leases: {},
    claims: [],
    contests: {},
    status: {},
    revealed: [],
    closed: [],
    people: { newcomer: person(), pv: person(), pvv: person(), maintainer: person() },
    next: 1,
  };
  const day = (d: number) => new Date(Date.now() - d * 86400000).toISOString();
  // Examples so that every role has something to see.
  const hpTotal = find("Mut.total", true);
  const realPos = find("Mut.pos_le", false);
  if (hpTotal) {
    s.claims.push({
      claim_id: "C-demo1",
      ticket_id: hpTotal,
      by: "other",
      status: "open",
      failed: ["fidelity"],
      reason:
        "The paper says 'a ≤ b or b < a'; the formal statement has a different relation in the second disjunct.",
    });
  }
  if (realPos) {
    s.claims.push({
      claim_id: "C-demo2",
      ticket_id: realPos,
      by: "other",
      status: "open",
      failed: ["edge_cases"],
      reason: "For n = 0 the conclusion 1 ≤ n fails, so the statement looks wrong at the edge.",
    });
  }
  const div = find("NavierStokes.Comparator.divergence", false);
  if (div) s.status[div] = "escalate";
  const qrh = find("OAI.riemannZeta_ne_zero_of_seven_eighths_lt_re", false);
  if (qrh)
    s.contests[qrh] = [
      "The passage is a paraphrase, not a quote: please map the theorem of the preprint with its number.",
    ];
  const hpPos = find("Mut.pos_le", true);
  const realDouble = find("Mut.double", false);
  for (const role of ["pv", "pvv", "maintainer"] as Role[]) {
    const p = s.people[role];
    if (hpPos) {
      p.history.push({
        declaration: "Mut.pos_le",
        paper: "Mutation fixture (demo)",
        verdict: "incorrect",
        duty: "review",
        submitted: day(9),
        outcome: "error",
        planted_error: true,
      });
      p.seen.push(hpPos, ...(realPos ? [realPos] : []));
    }
    if (realDouble) {
      p.history.push({
        declaration: "Mut.double",
        paper: "Mutation fixture (demo)",
        verdict: "correct",
        duty: "review",
        submitted: day(6),
        outcome: "accepted",
        planted_error: false,
      });
      p.seen.push(realDouble);
    }
  }
  return s;
}

function load(): State {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (raw) return JSON.parse(raw) as State;
  } catch {
    /* fresh state */
  }
  return fresh();
}
let state = load();
const save = () => sessionStorage.setItem(KEY, JSON.stringify(state));

export function currentRole(): Role {
  const t = localStorage.getItem(TOKEN);
  return (ROLES.find((r) => r.role === t)?.role ?? "newcomer") as Role;
}
export function switchRole(role: Role): void {
  localStorage.setItem(TOKEN, role);
  window.location.hash = "#/work";
  window.location.reload();
}
export function resetDemo(): void {
  sessionStorage.removeItem(KEY);
  localStorage.setItem(TOKEN, "newcomer");
  window.location.hash = "#/how";
  window.location.reload();
}

class HttpError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
const id = (prefix: string) => `${prefix}-demo${state.next++}`;
const now = () => new Date().toISOString();
const statusOf = (tid: string) => state.status[tid] ?? "open";
const isOpen = (tid: string) => {
  const entry = tickets.get(tid);
  return !!entry && statusOf(tid) === "open" && !state.closed.includes(entry.sub.submission_id);
};
const revealed = (tid: string) =>
  state.revealed.includes(tid) || state.closed.includes(tickets.get(tid)!.sub.submission_id);

function roleOf(auth: string | null): Role | null {
  const token = auth?.replace(/^Bearer\s+/, "") ?? "";
  return (ROLES.find((r) => r.role === token)?.role ?? null) as Role | null;
}

function activeLeases(role: Role): Lease[] {
  return Object.values(state.leases).filter((l) => l.role === role && l.status === "active");
}

function leaseJson(l: Lease): Json {
  const { t, sub } = tickets.get(l.ticket_id)!;
  const out: Json = {
    lease_id: l.lease_id,
    duty: l.duty,
    status: l.status,
    extendable: l.status === "active" && !l.extended,
    expected_minutes: null,
    min_reason_chars: snap.min_reason_chars,
    ticket: {
      ticket_id: t.ticket_id,
      paper: sub.title,
      repo_url: sub.repo_url,
      commit: sub.commit,
      domain: t.domain,
      tier: t.tier,
      view: t.view,
      questions: snap.questions[kindOf(t.decl_kind)],
      purpose: snap.purpose[kindOf(t.decl_kind)],
      paper_ref: sub.paper_ref,
      paper_passage: t.paper,
      mapping_contested_by_me: state.people[l.role].seen.includes(`contest:${t.ticket_id}`),
    },
  };
  if (l.duty === "claim" && l.claim_id) {
    const c = state.claims.find((x) => x.claim_id === l.claim_id)!;
    out.claim = { claim_id: c.claim_id, reason: c.reason, failed: c.failed, evidence: null };
  }
  return out;
}

function eligible(role: Role, tid: string): boolean {
  const { t } = tickets.get(tid)!;
  const p = state.people[role];
  if (!isOpen(tid) || p.seen.includes(tid)) return false;
  if (!PROFILE[role].tiers.includes(t.tier)) return false;
  const unitsInWork = activeLeases(role).map((l) => tickets.get(l.ticket_id)!.t.declaration);
  return !unitsInWork.includes(t.declaration);
}

function drawSet(role: Role): Json {
  const p = state.people[role];
  if (p.set && p.set.tickets.some((tid) => eligible(role, tid))) return setJson(p.set);
  const pool = [...tickets.keys()]
    .filter((tid) => eligible(role, tid))
    .sort(() => Math.random() - 0.5);
  const prefers = (tid: string) => {
    const { t } = tickets.get(tid)!;
    return (
      (!p.prefs.domains.length || p.prefs.domains.includes(t.domain)) &&
      (!p.prefs.tiers.length || p.prefs.tiers.includes(t.tier))
    );
  };
  let preferred = pool.filter(prefers);
  if (new Set(preferred.map((tid) => tickets.get(tid)!.sub.submission_id)).size < 2) preferred = [];
  const size = snap.choice_set_size;
  const picked: string[] = [];
  const decls = new Set<string>();
  for (const [src, limit] of [
    [preferred, Math.floor(size / 2)],
    [pool, size],
  ] as [string[], number][]) {
    for (const distinct of [true, false]) {
      const papers = new Set(picked.map((tid) => tickets.get(tid)!.sub.submission_id));
      for (const tid of src) {
        const { t, sub } = tickets.get(tid)!;
        if (picked.length >= limit || decls.has(t.declaration)) continue;
        if (distinct && papers.has(sub.submission_id)) continue;
        picked.push(tid);
        decls.add(t.declaration);
        papers.add(sub.submission_id);
      }
    }
  }
  picked.sort(() => Math.random() - 0.5);
  p.set = picked.length ? { set_id: id("CS"), tickets: picked } : null;
  return setJson(p.set);
}

function setJson(set: Person["set"]): Json {
  if (!set) return { set_id: null, tickets: [] };
  return {
    set_id: set.set_id,
    tickets: set.tickets.map((tid) => {
      const { t, sub } = tickets.get(tid)!;
      return {
        ticket_id: tid,
        declaration: t.declaration,
        decl_kind: t.decl_kind,
        domain: t.domain,
        tier: t.tier,
        paper: sub.title,
        expected_minutes: null,
      };
    }),
  };
}

function me(role: Role): Json {
  const prof = PROFILE[role];
  const p = state.people[role];
  const domains = [...new Set(snap.submissions.flatMap((s) => s.tickets.map((t) => t.domain)))];
  return {
    reviewer_id: `R-demo-${role}`,
    pseudonym: prof.pseudonym,
    group: prof.group,
    maintainer: prof.maintainer,
    roles: Object.fromEntries(domains.map((d) => [d, prof.roles])),
    reliability: role === "newcomer" ? 0.5 : 0.9,
    wip_limit: prof.wip,
    preferences: p.prefs,
    tiers_open: prof.tiers,
    leases: activeLeases(role).map(leaseJson),
    history: [...p.history].reverse(),
  };
}

function review(role: Role, l: Lease, body: Json): Json {
  const verdict = body.verdict as "correct" | "incorrect";
  const reason = String(body.reason ?? "").trim();
  const failed = (body.failed as string[] | undefined) ?? [];
  if (verdict === "incorrect" && !reason)
    throw new HttpError(400, "an 'incorrect' verdict needs a justification (SR-09)");
  if (verdict === "incorrect" && !failed.length)
    throw new HttpError(400, "an 'incorrect' verdict must name the question that fails (SR-09)");
  if (verdict === "incorrect" && reason.length < snap.min_reason_chars)
    throw new HttpError(
      400,
      `the justification needs at least ${snap.min_reason_chars} characters (SR-09)`,
    );
  if (body.ai_used && !body.ai_provider)
    throw new HttpError(400, "declared AI use must name the provider (SR-48)");
  const { t, sub } = tickets.get(l.ticket_id)!;
  l.status = "done";
  const p = state.people[role];
  p.seen.push(t.ticket_id);
  const item: HistoryItem = {
    declaration: t.declaration,
    paper: sub.title,
    verdict,
    duty: "review",
    submitted: now(),
    outcome: null,
    planted_error: null,
  };
  if (t.honeypot) {
    // The real system reveals planted errors days later, in batches (SR-37).
    state.revealed.push(t.ticket_id);
    item.planted_error = true;
    item.outcome = "error";
  } else if (verdict === "incorrect") {
    state.claims.push({
      claim_id: id("C"),
      ticket_id: t.ticket_id,
      by: role,
      reason,
      failed,
      status: "open",
    });
  }
  p.history.push(item);
  return { ok: true };
}

function nextDuty(role: Role): Json | null {
  if (!PROFILE[role].roles.includes("PVV")) throw new HttpError(403, "PVV role required (SR-13)");
  const held = activeLeases(role).find((l) => l.duty === "claim");
  if (held) return leaseJson(held);
  const claim = state.claims.find(
    (c) =>
      c.status === "open" &&
      c.by !== role &&
      !Object.values(state.leases).some((l) => l.claim_id === c.claim_id && l.status === "active"),
  );
  if (!claim) return null;
  const l: Lease = {
    lease_id: id("L"),
    role,
    ticket_id: claim.ticket_id,
    duty: "claim",
    claim_id: claim.claim_id,
    status: "active",
    extended: false,
  };
  state.leases[l.lease_id] = l;
  return leaseJson(l);
}

function resolveClaim(role: Role, l: Lease, body: Json): Json {
  if (!String(body.reason ?? "").trim())
    throw new HttpError(400, "a claim decision needs a justification");
  const c = state.claims.find((x) => x.claim_id === l.claim_id)!;
  c.status = body.confirmed ? "confirmed" : "rejected";
  l.status = "done";
  if (c.status === "confirmed") state.status[c.ticket_id] = "error";
  const { t, sub } = tickets.get(c.ticket_id)!;
  if (t.honeypot) state.revealed.push(t.ticket_id);
  state.people[role].history.push({
    declaration: t.declaration,
    paper: sub.title,
    verdict: body.confirmed ? "incorrect" : "correct",
    duty: "claim",
    submitted: now(),
    outcome: statusOf(c.ticket_id) === "open" ? null : statusOf(c.ticket_id),
    planted_error: t.honeypot && revealed(t.ticket_id) ? true : null,
  });
  if (c.by !== "other") {
    const h = state.people[c.by].history.find(
      (x) => x.declaration === t.declaration && x.verdict === "incorrect",
    );
    if (h) h.outcome = c.status === "confirmed" ? "error" : "claim rejected";
  }
  return { ok: true };
}

function admin(path: string, method: string, body: Json): unknown {
  if (path === "/api/admin/tick") return { expired: 0, revealed: 0 };
  if (path === "/api/admin/submissions") {
    return snap.submissions.map((s) => {
      const counts: Record<string, number> = {};
      for (const t of s.tickets) {
        const k = t.honeypot && revealed(t.ticket_id) ? "planted_error" : statusOf(t.ticket_id);
        counts[k] = (counts[k] ?? 0) + 1;
      }
      return {
        submission_id: s.submission_id,
        title: s.title,
        repo_url: s.repo_url,
        commit: s.commit,
        closed: state.closed.includes(s.submission_id),
        tickets: counts,
      };
    });
  }
  if (path === "/api/admin/escalated") {
    return [...tickets.values()]
      .filter(({ t }) => statusOf(t.ticket_id) === "escalate")
      .map(({ t, sub }) => ({
        ticket_id: t.ticket_id,
        declaration: t.declaration,
        paper: sub.title,
        votes: [
          { verdict: "correct", reason: "Trace of the derivative: the usual divergence." },
          { verdict: "correct", reason: "" },
          {
            verdict: "incorrect",
            reason:
              "fderiv is 0 where v is not differentiable, so the divergence is 0 there, not undefined.",
          },
        ],
      }));
  }
  if (path === "/api/admin/contested") {
    return Object.entries(state.contests)
      .filter(([, r]) => r.length)
      .map(([tid, reasons]) => {
        const { t, sub } = tickets.get(tid)!;
        return {
          ticket_id: tid,
          declaration: t.declaration,
          paper: sub.title,
          locator: String(t.paper?.locator ?? ""),
          reasons,
        };
      });
  }
  const decide = path.match(/^\/api\/admin\/tickets\/([^/]+)\/decide$/);
  if (decide && method === "POST") {
    state.status[decide[1]] = body.error ? "error" : "accepted";
    return { ok: true };
  }
  const close = path.match(/^\/api\/admin\/submissions\/([^/]+)\/close$/);
  if (close && method === "POST") {
    state.closed.push(close[1]);
    return { ok: true };
  }
  throw new HttpError(404, "not found");
}

function handle(method: string, path: string, body: Json, auth: string | null): unknown {
  if (path === "/api/auth/config")
    return { providers: [{ kind: "local", name: "local", label: "Access token" }] };
  if (path === "/api/notice") return snap.notice;
  if (path === "/api/register") {
    if (!body.notice_acknowledged)
      throw new HttpError(403, "registration requires acknowledging the notice (SR-49)");
    return { reviewer_id: "R-demo-newcomer", token: "newcomer" };
  }
  if (path === "/api/stats") {
    const counts: Record<string, number> = {};
    for (const tid of tickets.keys()) {
      const k = tickets.get(tid)!.t.honeypot && revealed(tid) ? "honeypot" : statusOf(tid);
      counts[k] = (counts[k] ?? 0) + 1;
    }
    return {
      reviewers: 4,
      reviewers_by_group: { student: 1, doctoral: 1, expert: 2 },
      submissions: snap.submissions.length,
      tickets_by_status: counts,
      reviews_last_7_days: Object.values(state.people).reduce((n, p) => n + p.history.length, 0),
      open_claims: state.claims.filter((c) => c.status === "open").length,
      active_leases: Object.values(state.leases).filter((l) => l.status === "active").length,
      audit_head: "demo",
    };
  }
  if (path === "/api/attention") return {};
  if (path === "/api/audit/head") return { length: 0, head_hash: null };
  const role = roleOf(auth);
  if (path === "/api/auth/session")
    return role
      ? { authenticated: true, provider: "local", registered: true }
      : { authenticated: false };
  if (!role) throw new HttpError(401, "missing bearer token");
  const p = state.people[role];
  if (path === "/api/me") return me(role);
  if (path === "/api/me/preferences") {
    p.prefs = { domains: (body.domains as string[]) ?? [], tiers: (body.tiers as string[]) ?? [] };
    p.set = null;
    return { ok: true };
  }
  if (path === "/api/me/affiliations") return { ok: true };
  if (path === "/api/domains")
    return [...new Set([...tickets.values()].map(({ t }) => t.domain))].sort();
  // Shown also at the work-in-progress limit; taking a ticket respects it.
  if (path === "/api/choice-set") return drawSet(role);
  if (path === "/api/leases" && method === "POST") {
    if (!p.set || p.set.set_id !== body.set_id || !p.set.tickets.includes(String(body.ticket_id)))
      throw new HttpError(409, "this choice set is no longer valid");
    if (activeLeases(role).length >= PROFILE[role].wip)
      throw new HttpError(409, "work-in-progress limit reached (SR-27)");
    const l: Lease = {
      lease_id: id("L"),
      role,
      ticket_id: String(body.ticket_id),
      duty: "review",
      claim_id: null,
      status: "active",
      extended: false,
    };
    state.leases[l.lease_id] = l;
    p.set = null;
    return leaseJson(l);
  }
  if (path === "/api/duties/next") return nextDuty(role);
  const blob = path.match(/^\/api\/blobs\/(.+)$/);
  if (blob) return "-- evidence files are not part of the click dummy";
  const m = path.match(/^\/api\/leases\/([^/]+)(?:\/([a-z-]+))?$/);
  if (m) {
    const l = state.leases[m[1]];
    if (!l || l.role !== role) throw new HttpError(404, "no such lease");
    const action = m[2];
    if (!action) return leaseJson(l);
    if (l.status !== "active") throw new HttpError(409, "this lease is not active");
    if (action === "extend") {
      l.extended = true;
      return leaseJson(l);
    }
    if (action === "return") {
      l.status = "returned";
      return { ok: true };
    }
    if (action === "review") return review(role, l, body);
    if (action === "claim") return resolveClaim(role, l, body);
    if (action === "contest-mapping") {
      const reason = String(body.reason ?? "").trim();
      if (reason.length < snap.min_reason_chars)
        throw new HttpError(
          400,
          `say what is wrong with the passage, in at least ${snap.min_reason_chars} characters`,
        );
      (state.contests[l.ticket_id] ??= []).push(reason);
      p.seen.push(`contest:${l.ticket_id}`);
      return { ok: true };
    }
  }
  if (path.startsWith("/api/admin/")) {
    if (!PROFILE[role].maintainer) throw new HttpError(403, "maintainers only");
    return admin(path, method, body);
  }
  throw new HttpError(404, "not found");
}

/** Answer /api/* requests in the browser; everything else goes out as usual. */
export function installMock(): void {
  if (!localStorage.getItem(TOKEN)) localStorage.setItem(TOKEN, "newcomer");
  const realFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const path = new URL(url, window.location.href).pathname.replace(/^.*?(\/api\/)/, "/api/");
    if (!path.startsWith("/api/")) return realFetch(input, init);
    const method = (init?.method ?? "GET").toUpperCase();
    const headers = new Headers(init?.headers);
    let body: Json = {};
    if (typeof init?.body === "string" && init.body) body = JSON.parse(init.body) as Json;
    try {
      const data = handle(method, path, body, headers.get("Authorization"));
      save();
      if (typeof data === "string")
        return new Response(data, { status: 200, headers: { "content-type": "text/plain" } });
      return new Response(JSON.stringify(data ?? null), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    } catch (e) {
      const status = e instanceof HttpError ? e.status : 500;
      return new Response(JSON.stringify({ detail: (e as Error).message }), {
        status,
        headers: { "content-type": "application/json" },
      });
    }
  };
}
