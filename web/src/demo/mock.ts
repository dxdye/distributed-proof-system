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
  root: string | null; // the main theorem
  basis: Json | null; // what the result relies on (C-29)
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
  // discussion after the decision (proposal C-25)
  posts: MockPost[];
  named: Record<string, string[]>; // thread key -> authors who show their pseudonym
  reopens: {
    request_id: string;
    ticket_id: string;
    reason: string;
    status: string;
  }[];
  decided_at: Record<string, string>; // ticket id -> when decided or revealed (progress page)
  thread_votes: Record<string, Record<string, number>>; // thread key -> voter -> ±1
};
type Author = Role | "ana" | "ben" | "carla";
type MockPost = {
  post_id: string;
  thread: string; // "<submission id>|<declaration>"
  author: Author;
  kind: "review" | "comment";
  text: string;
  verdict?: "correct" | "incorrect";
  failed?: string[];
  at: string;
  votes: Record<string, number>;
  reports: { by: string; reason: string }[];
  hidden: string | null;
  ai_used: boolean;
};
// Other members of the dummy community (their posts are seeded).
const OTHERS: Record<string, { pseudonym: string; maintainer: boolean; since: string }> = {
  ana: { pseudonym: "ana-k", maintainer: false, since: "2026-09" },
  ben: { pseudonym: "bpetersen", maintainer: false, since: "2026-11" },
  carla: { pseudonym: "carla-m", maintainer: true, since: "2026-06" },
};

export const ROLES: { role: Role; label: string; hint: string }[] = [
  {
    role: "newcomer",
    label: "Newcomer",
    hint: "New account: easy and medium tickets, no weight yet.",
  },
  {
    role: "pv",
    label: "Reviewer (PV)",
    hint: "Earned trust in the domains: hard tickets open.",
  },
  {
    role: "pvv",
    label: "Re-checker (PVV)",
    hint: "Re-checks verdicts and decides claims.",
  },
  {
    role: "maintainer",
    label: "Maintainer",
    hint: "Escalations, contested mappings, closing.",
  },
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
    version: 5,
    leases: {},
    claims: [],
    contests: {},
    status: {},
    revealed: [],
    closed: [],
    people: {
      newcomer: person(),
      pv: person(),
      pvv: person(),
      maintainer: person(),
    },
    next: 1,
    posts: [],
    named: {},
    reopens: [],
    decided_at: {},
    thread_votes: {},
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
  // Two decided declarations with an open discussion.
  const dbl = find("Mut.double", false);
  const win = find("Mut.window", false);
  if (dbl && win) {
    s.status[dbl] = "accepted";
    s.status[win] = "accepted";
    s.decided_at[dbl] = day(8);
    s.decided_at[win] = day(6);
    const key = (tid: string) =>
      `${tickets.get(tid)!.sub.submission_id}|${tickets.get(tid)!.t.declaration}`;
    const post = (
      thread: string,
      author: Author,
      kind: "review" | "comment",
      text: string,
      extra: Partial<MockPost> = {},
      votes: Record<string, number> = {},
    ) =>
      s.posts.push({
        post_id: `P-seed${s.posts.length + 1}`,
        thread,
        author,
        kind,
        text,
        at: day(5 - s.posts.length * 0.3),
        votes,
        reports: [],
        hidden: null,
        ai_used: false,
        ...extra,
      });
    post(
      key(dbl),
      "ana",
      "review",
      "Matches Definition 1 of the paper: 2 · n on the natural numbers. No edge cases, n = 0 gives 0 in both.",
      { verdict: "correct" },
      { ben: 1, carla: 1 },
    );
    post(
      key(dbl),
      "ben",
      "comment",
      "Worth noting: a mutated version of this definition (3 · n) would still typecheck. Only the comparison with the paper catches it.",
      {},
      { ana: 1 },
    );
    post(
      key(dbl),
      "carla",
      "comment",
      "Agreed. For definitions like this, a short definition test (double 1 = 2) would make the check mechanical. See the error catalogue.",
      {},
      { ana: 1, ben: 1 },
    );
    s.named[key(dbl)] = ["carla"];
    post(
      key(win),
      "ben",
      "review",
      "The hypotheses 2 ≤ n and n < 3 together force n = 2, so the statement is not vacuous, just narrow. Faithful to Lemma 6.",
      { verdict: "correct" },
      { ana: 1 },
    );
    post(
      key(win),
      "ana",
      "comment",
      "Is a lemma this narrow worth a class-A ticket at all? It is used in the main theorem, so yes.",
      {},
      {},
    );
  }
  // Notes by maintainers on the progress page (proposal C-26).
  const note = (sid: string, text: string, at: string, votes: Record<string, number>) =>
    s.posts.push({
      post_id: `P-seed${s.posts.length + 1}`,
      thread: `${sid}|`,
      author: "carla",
      kind: "comment",
      text,
      at,
      votes,
      reports: [],
      hidden: null,
      ai_used: false,
    });
  note(
    "S-mutation",
    "The main statement (Mut.window) is confirmed faithful: the paper is at PRL 2. The remaining declarations of class A are next; the definitions matter most.",
    day(5.5),
    { ana: 1, ben: 1 },
  );
  note(
    "S-ns",
    "The declaration to watch is the definition of a smooth solution: one condition too few, and the main theorem is about something else. One divergence check is escalated to the maintainers.",
    day(3),
    { ana: 1 },
  );
  s.named["S-ns|"] = ["carla"];

  // Navier–Stokes: two decided declarations with a discussion. Both are about
  // how Mathlib's definitions are used (proposal C-27).
  const nsPost = (
    decl: string,
    author: Author,
    text: string,
    at: string,
    votes: Record<string, number>,
  ) =>
    s.posts.push({
      post_id: `P-seed${s.posts.length + 1}`,
      thread: `S-ns|NavierStokes.Comparator.${decl}`,
      author,
      kind: "comment",
      text,
      at,
      votes,
      reports: [],
      hidden: null,
      ai_used: false,
    });
  const ivc = find("NavierStokes.Comparator.InitialVelocityCondition", false);
  const ivcd = find("NavierStokes.Comparator.InitialVelocityConditionDecay", false);
  if (ivc && ivcd) {
    s.status[ivc] = "accepted";
    s.status[ivcd] = "accepted";
    s.decided_at[ivc] = day(4);
    s.decided_at[ivcd] = day(2.5);
    nsPost(
      "InitialVelocityCondition",
      "ben",
      "Divergence-free and smooth, as in the paper; the decay of u₀ is a separate structure (InitialVelocityConditionDecay), as in Fefferman's formulation.",
      day(3.9),
      { ana: 1 },
    );
    nsPost(
      "InitialVelocityCondition",
      "ana",
      "Two conventions of Mathlib meet here. ContDiff takes a smoothness level in WithTop ℕ∞: the ↑⊤ in the statement is ⊤ : ℕ∞ coerced, which is C^∞; the plain ⊤ would mean analytic. And fderiv is 0 where a function is not differentiable, so divergence u₀ x = 0 alone would also accept a field that is nowhere differentiable. The ContDiff condition rules that out.",
      day(3.7),
      { ben: 1, carla: 1 },
    );
    nsPost(
      "InitialVelocityCondition",
      "carla",
      "Exactly the kind of check the review should make: not only whether a Mathlib definition is the right one, but how it is used. Accepted.",
      day(3.5),
      { ana: 1 },
    );
    nsPost(
      "InitialVelocityConditionDecay",
      "ana",
      "Fefferman asks |∂^α u₀(x)| ≤ C_αK (1 + |x|)^(−K) for every α and K. Here: ‖iteratedFDeriv ℝ m u₀ x‖ ≤ C / (1 + ‖x‖)^K for every order m and every K. The norm of the m-th derivative bounds every partial derivative of order m, so both say the same up to the constant.",
      day(2.4),
      { ben: 1, carla: 1 },
    );
    nsPost(
      "InitialVelocityConditionDecay",
      "ben",
      "And the constant comes after ∀ m K, so it may depend on m and K, as C_αK does in the paper. With ∃ C in front, the condition would be far stronger.",
      day(2.2),
      { ana: 1 },
    );
    s.named["S-ns|NavierStokes.Comparator.InitialVelocityCondition"] = ["carla"];
  }
  return s;
}

function load(): State {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as State;
      if (parsed.version === 5) return parsed;
    }
  } catch {
    /* fresh state */
  }
  return fresh();
}
let state = load();
const save = () => sessionStorage.setItem(KEY, JSON.stringify(state));

export function currentRole(): Role | null {
  const t = localStorage.getItem(TOKEN);
  return (ROLES.find((r) => r.role === t)?.role ?? null) as Role | null;
}
export function switchRole(role: Role): void {
  localStorage.setItem(TOKEN, role);
  window.location.hash = "#/work";
  window.location.reload();
}
export function resetDemo(): void {
  sessionStorage.removeItem(KEY);
  localStorage.removeItem(TOKEN); // signed out: the front page
  window.location.hash = "#/";
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
    out.claim = {
      claim_id: c.claim_id,
      reason: c.reason,
      failed: c.failed,
      evidence: null,
    };
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
    pvv_waiting: prof.roles.includes("PVV")
      ? state.claims.filter(
          (c) =>
            c.status === "open" &&
            c.by !== role &&
            !Object.values(state.leases).some(
              (l) => l.claim_id === c.claim_id && l.status === "active",
            ),
        ).length
      : 0,
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
    state.decided_at[t.ticket_id] = now();
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
  if (c.status === "confirmed" || t.honeypot) state.decided_at[c.ticket_id] = now();
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
  if (path === "/api/admin/reports") {
    return state.posts
      .filter((p) => p.reports.length && !p.hidden)
      .map((p) => {
        const [sid, decl] = p.thread.split("|");
        return {
          post_id: p.post_id,
          submission_id: sid,
          declaration: decl,
          text: p.text,
          kind: p.kind,
          reasons: p.reports.map((r) => r.reason),
        };
      });
  }
  const hide = path.match(/^\/api\/admin\/posts\/([^/]+)\/hide$/);
  if (hide) {
    const p = state.posts.find((x) => x.post_id === hide[1]);
    if (p) p.hidden = String(body.reason ?? "");
    return { ok: true };
  }
  if (path === "/api/admin/reopens") {
    return state.reopens
      .filter((q) => q.status === "open")
      .map((q) => {
        const { t, sub } = tickets.get(q.ticket_id)!;
        return {
          request_id: q.request_id,
          ticket_id: q.ticket_id,
          declaration: t.declaration,
          paper: sub.title,
          submission_id: sub.submission_id,
          outcome: statusOf(q.ticket_id),
          reason: q.reason,
        };
      });
  }
  const res = path.match(/^\/api\/admin\/reopens\/([^/]+)$/);
  if (res && method === "POST") {
    const q = state.reopens.find((x) => x.request_id === res[1]);
    if (!q) throw new HttpError(409, "no open reopen request with this id");
    q.status = body.reopen ? "reopened" : "dismissed";
    if (body.reopen) state.status[q.ticket_id] = "escalate";
    return { ok: true };
  }
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
          {
            verdict: "correct",
            reason: "Trace of the derivative: the usual divergence.",
          },
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
    state.decided_at[decide[1]] = now();
    return { ok: true };
  }
  const close = path.match(/^\/api\/admin\/submissions\/([^/]+)\/close$/);
  if (close && method === "POST") {
    state.closed.push(close[1]);
    return { ok: true };
  }
  throw new HttpError(404, "not found");
}

// --------------------------------------------- discussion after the decision
const threadKey = (sid: string, decl: string) => `${sid}|${decl}`;
function realTicket(sid: string, decl: string): SnapTicket | undefined {
  const sub = snap.submissions.find((x) => x.submission_id === sid);
  return sub?.tickets.find((t) => t.declaration === decl && !t.honeypot);
}
function threadOpen(sid: string, decl: string): boolean {
  const real = realTicket(sid, decl);
  return !!real && ["accepted", "error"].includes(statusOf(real.ticket_id));
}
function openThreads(): [string, string][] {
  const out: [string, string][] = [];
  for (const sub of snap.submissions)
    for (const t of sub.tickets)
      if (!t.honeypot && threadOpen(sub.submission_id, t.declaration))
        out.push([sub.submission_id, t.declaration]);
  return out;
}
function canShare(role: Role, sid: string, decl: string): boolean {
  const reviewed = state.people[role].history.some(
    (h) => h.declaration === decl && h.duty === "review" && !h.planted_error,
  );
  const shared = state.posts.some(
    (p) => p.thread === threadKey(sid, decl) && p.author === role && p.kind === "review",
  );
  return reviewed && !shared;
}
function threadJson(role: Role, sid: string, decl: string): Json {
  const real = realTicket(sid, decl)!;
  const sub = snap.submissions.find((x) => x.submission_id === sid)!;
  const key = threadKey(sid, decl);
  const posts = state.posts.filter((p) => p.thread === key);
  const order: string[] = [];
  for (const p of posts) if (!order.includes(p.author)) order.push(p.author);
  const named = state.named[key] ?? [];
  const label = (a: string) =>
    named.includes(a)
      ? (OTHERS[a]?.pseudonym ?? PROFILE[a as Role].pseudonym)
      : `Reviewer ${String.fromCharCode(65 + order.indexOf(a))}`;
  const reviewedHere = (a: string) =>
    posts.some((p) => p.author === a && p.kind === "review") ||
    (a in PROFILE &&
      state.people[a as Role].history.some((h) => h.declaration === decl && h.duty === "review"));
  const out = posts.map((p) => ({
    post_id: p.post_id,
    kind: p.kind,
    author: label(p.author),
    is_me: p.author === role,
    maintainer: OTHERS[p.author]?.maintainer ?? PROFILE[p.author as Role].maintainer,
    member_since: OTHERS[p.author]?.since ?? "2026-11",
    reviewed_here: reviewedHere(p.author),
    at: p.at,
    score: Object.values(p.votes).reduce((a, b) => a + b, 0),
    my_vote: p.votes[role] ?? 0,
    ai_used: p.ai_used,
    hidden: p.hidden,
    reported_by_me: p.reports.some((r) => r.by === role),
    text: p.hidden ? "" : p.text,
    ...(p.kind === "review" && !p.hidden
      ? { verdict: p.verdict, reason: p.text, failed: p.failed ?? [] }
      : {}),
  }));
  out.sort((a, b) => b.score - a.score || a.at.localeCompare(b.at));
  return {
    submission_id: sid,
    declaration: decl,
    decl_kind: real.decl_kind,
    paper: sub.title,
    repo_url: sub.repo_url,
    commit: sub.commit,
    domain: real.domain,
    outcome: statusOf(real.ticket_id),
    decided_at: null,
    view: real.view,
    paper_passage: real.paper,
    me: {
      label: order.includes(role) ? label(role) : null,
      named: named.includes(role),
      can_share: canShare(role, sid, decl),
      reviewed_here: reviewedHere(role),
    },
    reopen_pending: state.reopens.some(
      (q) => q.ticket_id === real.ticket_id && q.status === "open",
    ),
    score: Object.values(state.thread_votes[key] ?? {}).reduce((a, b) => a + b, 0),
    my_vote: state.thread_votes[key]?.[role] ?? 0,
    posts: out,
  };
}
function discussion(
  role: Role,
  _method: string,
  path: string,
  body: Json,
  query: URLSearchParams,
): unknown {
  if (path === "/api/discussions") {
    return openThreads()
      .map(([sid, decl]) => {
        const real = realTicket(sid, decl)!;
        const posts = state.posts.filter((p) => p.thread === threadKey(sid, decl) && !p.hidden);
        return {
          submission_id: sid,
          declaration: decl,
          decl_kind: real.decl_kind,
          paper: snap.submissions.find((x) => x.submission_id === sid)!.title,
          domain: real.domain,
          outcome: statusOf(real.ticket_id),
          posts: posts.length,
          last_activity:
            posts
              .map((p) => p.at)
              .sort()
              .pop() ?? "",
          can_share: canShare(role, sid, decl),
          score: Object.values(state.thread_votes[threadKey(sid, decl)] ?? {}).reduce(
            (a, b) => a + b,
            0,
          ),
          my_vote: state.thread_votes[threadKey(sid, decl)]?.[role] ?? 0,
        };
      })
      .sort((a, b) => b.score - a.score || b.last_activity.localeCompare(a.last_activity));
  }
  if (path === "/api/thread") {
    const sid = query.get("submission_id") ?? "",
      decl = query.get("declaration") ?? "";
    if (!threadOpen(sid, decl))
      throw new HttpError(403, "the discussion of this declaration is not open yet");
    return threadJson(role, sid, decl);
  }
  const sid = String(body.submission_id ?? ""),
    decl = String(body.declaration ?? "");
  const key = threadKey(sid, decl);
  const name = () => {
    if (body.show_pseudonym && !(state.named[key] ?? []).includes(role))
      (state.named[key] ??= []).push(role);
  };
  if (path === "/api/thread/posts") {
    if (!threadOpen(sid, decl))
      throw new HttpError(403, "the discussion opens once the declaration is decided");
    const text = String(body.text ?? "").trim();
    if (!text) throw new HttpError(400, "a post has 1 to 5000 characters");
    name();
    state.posts.push({
      post_id: id("P"),
      thread: key,
      author: role,
      kind: "comment",
      text,
      at: now(),
      votes: {},
      reports: [],
      hidden: null,
      ai_used: !!body.ai_used,
    });
    return { ok: true };
  }
  if (path === "/api/thread/share") {
    if (!canShare(role, sid, decl))
      throw new HttpError(404, "you have no review of this declaration to share");
    const h = state.people[role].history.find(
      (x) => x.declaration === decl && x.duty === "review",
    )!;
    name();
    state.posts.push({
      post_id: id("P"),
      thread: key,
      author: role,
      kind: "review",
      text: h.verdict === "correct" ? "Faithful to the paper." : "Problem found.",
      verdict: h.verdict,
      at: now(),
      votes: {},
      reports: [],
      hidden: null,
      ai_used: false,
    });
    return { ok: true };
  }
  if (path === "/api/thread/vote") {
    if (!threadOpen(sid, decl))
      throw new HttpError(403, "the discussion opens once the declaration is decided");
    const v = Number(body.value);
    const votes = (state.thread_votes[key] ??= {});
    if (v) votes[role] = v;
    else delete votes[role];
    return { ok: true };
  }
  if (path === "/api/thread/reopen") {
    const reason = String(body.reason ?? "").trim();
    if (reason.length < snap.min_reason_chars)
      throw new HttpError(
        400,
        `say what is wrong, in at least ${snap.min_reason_chars} characters`,
      );
    state.reopens.push({
      request_id: id("RQ"),
      ticket_id: realTicket(sid, decl)!.ticket_id,
      reason,
      status: "open",
    });
    return { ok: true };
  }
  const m = path.match(/^\/api\/posts\/([^/]+)\/(vote|report)$/);
  if (m) {
    const p = state.posts.find((x) => x.post_id === m[1]);
    if (!p) throw new HttpError(404, "no such post");
    if (m[2] === "vote") {
      if (p.author === role) throw new HttpError(400, "you cannot vote on your own post");
      const v = Number(body.value);
      if (v) p.votes[role] = v;
      else delete p.votes[role];
    } else if (_method === "DELETE") {
      if (!p.reports.some((r) => r.by === role))
        throw new HttpError(404, "you have not reported this post");
      p.reports = p.reports.filter((r) => r.by !== role);
    } else {
      if (p.reports.some((r) => r.by === role))
        throw new HttpError(409, "you have already reported this post");
      p.reports.push({ by: role, reason: String(body.reason ?? "") });
    }
    return { ok: true };
  }
  return undefined;
}

// ------------------------------------------------ public progress page (C-26)
// Counts by declaration; a declaration is decided when its real ticket is and
// every planted copy is revealed. The dummy does not run the decision rule, so
// the residual error uses a nominal posterior per accepted declaration.
const NOMINAL_P_ERROR = 0.004;
const OPENED = new Date(Date.now() - 14 * 86400000).toISOString();
const PRL_MEANING = [
  "claim only",
  "formalized, builds, standard axioms only",
  "main statement confirmed faithful",
  "all class-A declarations reviewed",
  "proof internals certified",
  "accepted by the community",
];
type Passage = {
  source: { url: string | null };
  locator: string;
  statement: string;
};
type Unit = { decl: string; real: SnapTicket; all: SnapTicket[] };

function unitsOf(sub: SnapSubmission): Unit[] {
  const by = new Map<string, SnapTicket[]>();
  for (const t of sub.tickets) by.set(t.declaration, [...(by.get(t.declaration) ?? []), t]);
  return [...by].map(([decl, all]) => ({
    decl,
    all,
    real: all.find((t) => !t.honeypot) ?? all[0],
  }));
}
const ticketDecided = (t: SnapTicket) =>
  t.honeypot ? revealed(t.ticket_id) : ["accepted", "error"].includes(statusOf(t.ticket_id));
function unitState(u: Unit): string {
  if (u.all.every(ticketDecided)) return statusOf(u.real.ticket_id);
  const ids = u.all.map((t) => t.ticket_id);
  const started =
    Object.values(state.people).some((p) => p.seen.some((x) => ids.includes(x))) ||
    Object.values(state.leases).some((l) => ids.includes(l.ticket_id)) ||
    ids.some((x) => statusOf(x) !== "open");
  return started ? "in review" : "not started";
}

function progressSummary(sub: SnapSubmission): Json {
  const us = unitsOf(sub);
  const states = us.map(unitState);
  const count = (s: string) => states.filter((x) => x === s).length;
  const accepted = count("accepted"),
    errors = count("error");
  const root = us.findIndex((u) => u.decl === sub.root);
  const prl = errors
    ? 1
    : us.length && accepted === us.length
      ? 3
      : root >= 0 && states[root] === "accepted"
        ? 2
        : 1;
  const paper = root >= 0 ? (us[root].real.paper as Passage | null) : null;
  return {
    submission_id: sub.submission_id,
    title: sub.title,
    repo_url: sub.repo_url,
    commit: sub.commit,
    paper_ref: sub.paper_ref,
    paper_url: paper?.source.url ?? sub.paper_ref ?? null,
    opened: OPENED,
    closed: state.closed.includes(sub.submission_id),
    prl,
    prl_meaning: PRL_MEANING[prl],
    declarations: us.length,
    decided: accepted + errors,
    accepted,
    errors,
    in_review: count("in review"),
    not_started: count("not started"),
    coverage: us.length ? (accepted + errors) / us.length : 0,
    residual_error: accepted ? 1 - (1 - NOMINAL_P_ERROR) ** accepted : null,
    forecast: null,
    interest: null,
    main_statement: paper?.statement ?? null,
    main_locator: paper?.locator ?? null,
  };
}

function notesJson(role: Role | null, sid: string): Json[] {
  const key = threadKey(sid, "");
  const posts = state.posts.filter((p) => p.thread === key);
  const order: string[] = [];
  for (const p of posts) if (!order.includes(p.author)) order.push(p.author);
  const named = state.named[key] ?? [];
  const out = posts.map((p) => ({
    post_id: p.post_id,
    kind: "comment",
    author: named.includes(p.author)
      ? (OTHERS[p.author]?.pseudonym ?? PROFILE[p.author as Role].pseudonym)
      : `Maintainer ${String.fromCharCode(65 + order.indexOf(p.author))}`,
    is_me: p.author === role,
    maintainer: true,
    member_since: OTHERS[p.author]?.since ?? "2026-11",
    reviewed_here: false,
    at: p.at,
    score: Object.values(p.votes).reduce((a, b) => a + b, 0),
    my_vote: role ? (p.votes[role] ?? 0) : 0,
    ai_used: p.ai_used,
    hidden: p.hidden,
    reported_by_me: role ? p.reports.some((r) => r.by === role) : false,
    text: p.hidden ? "" : p.text,
  }));
  out.sort((a, b) => b.score - a.score || a.at.localeCompare(b.at));
  return out;
}

function progressDetail(role: Role | null, sub: SnapSubmission): Json {
  const sid = sub.submission_id;
  const us = unitsOf(sub);
  const root = us.find((u) => u.decl === sub.root);
  const decidedAt = (u: Unit) =>
    u.all
      .map((t) => state.decided_at[t.ticket_id] ?? now())
      .sort()
      .pop()!;
  const times = us
    .filter((u) => ["accepted", "error"].includes(unitState(u)))
    .map(decidedAt)
    .sort();
  const closed = state.closed.includes(sid);
  return {
    ...progressSummary(sub),
    root: sub.root,
    main_view: root && threadOpen(sid, root.decl) ? root.real.view : null,
    units: us
      .map((u) => ({
        declaration: u.decl,
        decl_kind: u.real.decl_kind,
        tier: u.real.tier,
        domain: u.real.domain,
        state: unitState(u),
        discussion: threadOpen(sid, u.decl),
      }))
      .sort(
        (a, b) =>
          Number(a.declaration !== sub.root) - Number(b.declaration !== sub.root) ||
          a.declaration.localeCompare(b.declaration),
      ),
    basis: sub.basis ?? null,
    library_definitions: libraryDefinitions(role, sub),
    timeline: [
      { at: OPENED, decided: 0 },
      ...times.map((at, i) => ({ at, decided: i + 1 })),
      ...(closed ? [] : [{ at: now(), decided: times.length }]),
    ],
    notes: notesJson(role, sid),
  };
}

// A declaration as its reviewers see it, for maintainers.
function declarationJson(query: URLSearchParams): Json {
  const sid = query.get("submission_id") ?? "",
    decl = query.get("declaration") ?? "";
  const sub = snap.submissions.find((x) => x.submission_id === sid);
  const u = sub && unitsOf(sub).find((x) => x.decl === decl);
  if (!sub || !u) throw new HttpError(404, "no such declaration");
  const times = u.all.map((t) => state.decided_at[t.ticket_id]).filter(Boolean);
  const st = unitState(u);
  return {
    submission_id: sid,
    declaration: decl,
    decl_kind: u.real.decl_kind,
    tier: u.real.tier,
    domain: u.real.domain,
    state: st,
    decided_at: ["accepted", "error"].includes(st) && times.length ? times.sort().pop() : null,
    paper: sub.title,
    repo_url: sub.repo_url,
    commit: sub.commit,
    paper_ref: sub.paper_ref,
    paper_passage: u.real.paper,
    view: u.real.view,
    questions: snap.questions[kindOf(u.real.decl_kind)],
    purpose: snap.purpose[kindOf(u.real.decl_kind)],
    contested: (state.contests[u.real.ticket_id] ?? []).length,
    discussion: threadOpen(sid, decl),
  };
}

// Library definitions the statements use (C-27); hidden while a planted error
// of the paper is unrevealed, as in the real system.
type Gloss = { name: string; type: string; origin?: string; doc?: string; note?: string };
function libraryDefinitions(role: Role | null, sub: SnapSubmission): Json[] | null {
  const hidden = sub.tickets.some((t) => t.honeypot && !revealed(t.ticket_id));
  if (hidden && !(role && PROFILE[role].maintainer)) return null;
  const found = new Map<string, Json & { used_by: string[] }>();
  for (const u of unitsOf(sub)) {
    const comps = (u.real.view.components ?? []) as {
      glossary?: Gloss[];
      trusted_glossary?: Gloss[];
    }[];
    for (const c of comps)
      for (const g of c.trusted_glossary?.length ? c.trusted_glossary : (c.glossary ?? [])) {
        if (g.origin !== "library" && g.origin !== "core") continue;
        const d = found.get(g.name) ?? {
          name: g.name,
          type: g.type,
          origin: g.origin,
          doc: g.doc ?? null,
          note: g.note ?? null,
          used_by: [],
          reviewed: false,
        };
        if (!d.used_by.includes(u.decl)) d.used_by.push(u.decl);
        found.set(g.name, d);
      }
  }
  return [...found.values()].sort(
    (a, b) =>
      Number(a.origin !== "library") - Number(b.origin !== "library") ||
      String(a.name).localeCompare(String(b.name)),
  );
}

function progress(role: Role | null, sidRaw: string | undefined, notes: boolean, body: Json) {
  if (!sidRaw) return snap.submissions.map(progressSummary);
  const sid = decodeURIComponent(sidRaw);
  const sub = snap.submissions.find((x) => x.submission_id === sid);
  if (!sub) throw new HttpError(404, "no such submission");
  if (!notes) return progressDetail(role, sub);
  if (!role) throw new HttpError(401, "missing bearer token");
  if (!PROFILE[role].maintainer) throw new HttpError(403, "maintainers only");
  const text = String(body.text ?? "").trim();
  if (!text) throw new HttpError(400, "a post has 1 to 5000 characters");
  const key = threadKey(sid, "");
  if (body.show_pseudonym && !(state.named[key] ?? []).includes(role))
    (state.named[key] ??= []).push(role);
  const post_id = id("P");
  state.posts.push({
    post_id,
    thread: key,
    author: role,
    kind: "comment",
    text,
    at: now(),
    votes: {},
    reports: [],
    hidden: null,
    ai_used: false,
  });
  return { post_id };
}

function handle(
  method: string,
  path: string,
  body: Json,
  auth: string | null,
  query: URLSearchParams = new URLSearchParams(),
): unknown {
  if (path === "/api/auth/config")
    return {
      providers: [{ kind: "local", name: "local", label: "Access token" }],
    };
  if (path === "/api/notice") return snap.notice;
  if (path === "/api/register") {
    if (!body.notice_acknowledged)
      throw new HttpError(403, "registration requires acknowledging the notice (SR-49)");
    return { reviewer_id: "R-demo-newcomer", token: "newcomer" };
  }
  if (path === "/api/stats") {
    // No ticket counts (see Coordinator.stats).
    const planted = [...tickets.keys()].filter((t) => tickets.get(t)!.t.honeypot && revealed(t));
    return {
      reviewers: 4,
      reviewers_by_group: { student: 1, doctoral: 1, expert: 2 },
      submissions: snap.submissions.length,
      planted_errors_revealed: planted.length,
      reviews_last_7_days: Object.values(state.people).reduce((n, p) => n + p.history.length, 0),
      open_claims: state.claims.filter((c) => c.status === "open").length,
      active_leases: Object.values(state.leases).filter((l) => l.status === "active").length,
      audit_head: "demo",
    };
  }
  if (path === "/api/attention") return {};
  if (path === "/api/audit/head") return { length: 0, head_hash: null };
  const role = roleOf(auth);
  const prog = path.match(/^\/api\/progress(?:\/([^/]+))?(\/notes)?$/);
  if (prog) return progress(role, prog[1], !!prog[2], body);
  if (path === "/api/auth/session")
    return role
      ? { authenticated: true, provider: "local", registered: true }
      : { authenticated: false };
  if (!role) throw new HttpError(401, "missing bearer token");
  const p = state.people[role];
  if (path === "/api/me") return me(role);
  if (path === "/api/me/preferences") {
    p.prefs = {
      domains: (body.domains as string[]) ?? [],
      tiers: (body.tiers as string[]) ?? [],
    };
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
  if (
    path.startsWith("/api/discussions") ||
    path.startsWith("/api/thread") ||
    path.startsWith("/api/posts/")
  ) {
    const out = discussion(role, method, path, body, query);
    if (out !== undefined) return out;
  }
  if (path.startsWith("/api/admin/")) {
    if (!PROFILE[role].maintainer) throw new HttpError(403, "maintainers only");
    if (path === "/api/admin/declaration") return declarationJson(query);
    return admin(path, method, body);
  }
  throw new HttpError(404, "not found");
}

/** Answer /api/* requests in the browser; everything else goes out as usual. */
export function installMock(): void {
  const realFetch = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const parsed = new URL(url, window.location.href);
    const path = parsed.pathname.replace(/^.*?(\/api\/)/, "/api/");
    if (!path.startsWith("/api/")) return realFetch(input, init);
    const method = (init?.method ?? "GET").toUpperCase();
    const headers = new Headers(init?.headers);
    let body: Json = {};
    if (typeof init?.body === "string" && init.body) body = JSON.parse(init.body) as Json;
    try {
      const data = handle(method, path, body, headers.get("Authorization"), parsed.searchParams);
      save();
      if (typeof data === "string")
        return new Response(data, {
          status: 200,
          headers: { "content-type": "text/plain" },
        });
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
