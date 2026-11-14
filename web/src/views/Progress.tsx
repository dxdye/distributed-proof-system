import { useCallback, useEffect, useState } from "react";
import {
  api,
  type Me,
  type ProgressDetail,
  type ProgressSummary,
  type ProgressUnit,
  type Stats,
} from "../api";
import { Basis } from "../components/Basis";
import { Infoview } from "../components/Infoview";
import { MathText } from "../components/MathText";
import { ProgressChart } from "../components/ProgressChart";
import { TierBadge } from "../components/Tier";
import { PostCard, threadHref } from "./Discussions";

// The public progress page (proposal C-26, S-23): how far the review of every
// submission has come, for everyone, signed in or not. Counts are by
// declaration, never by ticket, and a declaration counts as decided only when
// all of its tickets are; open work shows no verdicts. Concept §10.1, §11.1.

export const progressHref = (sid: string) => `#/progress/${encodeURIComponent(sid)}`;

const PRL: [number, string, string][] = [
  [0, "Claim", "A paper claims the result."],
  [1, "Formalized", "The formalization builds and uses only the standard axioms."],
  [
    2,
    "Main statement faithful",
    "Reviewers confirmed that the main theorem says what the paper says.",
  ],
  [
    3,
    "Class A complete",
    "Every statement and definition the main theorem depends on is reviewed.",
  ],
  [4, "Proof internals certified", "Selected parts of the proof are reviewed as well (class B)."],
  [5, "Accepted", "The community accepts the result."],
];

const STATES: { key: ProgressUnit["state"]; label: string; icon: string }[] = [
  { key: "accepted", label: "accepted", icon: "✓" },
  { key: "error", label: "error found", icon: "✕" },
  { key: "in review", label: "in review", icon: "◐" },
  { key: "not started", label: "not started", icon: "○" },
];

const stateClass = (s: string) => `st-${s.replace(" ", "-")}`;

function pct(x: number): string {
  if (x === 0) return "0%";
  if (x < 0.01) return "<1%";
  if (x > 0.99 && x < 1) return ">99%";
  return `${Math.round(x * 100)}%`;
}

function residual(x: number | null): string {
  if (x === null) return "none accepted yet";
  if (x < 0.001) return "<0.1%";
  return `${(x * 100).toFixed(1)}%`;
}

function weeks(f: ProgressSummary["forecast"]): string {
  if (!f) return "not measured yet";
  const a = Math.max(1, Math.round(f.p50_weeks));
  const b = Math.max(a, Math.round(f.p85_weeks));
  return a === b ? `about ${a} ${a === 1 ? "week" : "weeks"}` : `${a}–${b} weeks`;
}

function interest(psi: number | null): string {
  return psi === null ? "no choices yet" : `${Math.exp(psi).toFixed(1)}× the average`;
}

function counts(s: ProgressSummary): Record<ProgressUnit["state"], number> {
  return {
    accepted: s.accepted,
    error: s.errors,
    "in review": s.in_review,
    "not started": s.not_started,
  };
}

function StatusBar({ s }: { s: ProgressSummary }) {
  const c = counts(s);
  const total = Math.max(s.declarations, 1);
  return (
    <div className="status">
      <div
        className="status-bar"
        role="img"
        aria-label={STATES.map((st) => `${c[st.key]} ${st.label}`).join(", ")}
      >
        {STATES.filter((st) => c[st.key] > 0).map((st) => (
          <span
            key={st.key}
            className={stateClass(st.key)}
            style={{ flexGrow: c[st.key] / total }}
          />
        ))}
      </div>
      <ul className="status-legend">
        {STATES.map((st) => (
          <li key={st.key}>
            <span className={`swatch ${stateClass(st.key)}`} aria-hidden="true" />
            <span className="icon" aria-hidden="true">
              {st.icon}
            </span>
            {st.label} <strong>{c[st.key]}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PrlBadge({ s }: { s: ProgressSummary }) {
  return (
    <span className="badge prl" title={s.prl_meaning}>
      PRL {s.prl} · {PRL[s.prl][1]}
    </span>
  );
}

function Facts({ s }: { s: ProgressSummary }) {
  return (
    <dl className="kv facts">
      <dt>Confirmed findings</dt>
      <dd>{s.errors}</dd>
      <dt title="The probability that at least one accepted declaration is wrong after all, from the decision rule. As good as the calibration of the reviewers, which planted errors measure.">
        Residual error (estimate)
      </dt>
      <dd>{residual(s.residual_error)}</dd>
      <dt title="Time until class A is decided, at the measured pace of the last weeks: median (P50) to 85th percentile (P85).">
        Forecast
      </dt>
      <dd>{weeks(s.forecast)}</dd>
      <dt title="How often reviewers choose this paper when it is offered, weighted by their trust (Plackett–Luce).">
        Interest
      </dt>
      <dd>{interest(s.interest)}</dd>
    </dl>
  );
}

export function ProgressList({ me }: { me: Me | null }) {
  const [list, setList] = useState<ProgressSummary[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.progress().then(setList, (e) => setError((e as Error).message));
    api.stats().then(setStats, () => setStats(null));
  }, []);
  if (error) return <p className="error">{error}</p>;
  if (!list) return <p className="muted">Loading…</p>;
  const decls = list.reduce((n, s) => n + s.declarations, 0);
  const decided = list.reduce((n, s) => n + s.decided, 0);
  const found = list.reduce((n, s) => n + s.errors, 0);
  return (
    <div className="progress-page">
      <section className="hero">
        <span className="eyebrow">Progress</span>
        <h2>How far the review of every paper has come</h2>
        <p className="lead">
          Live, for everyone. Each paper is taken apart into the statements and definitions that
          need human judgement; this page shows how many of them reviewers have decided, what they
          found, and how sure the result is.
        </p>
        <p className="progress-total">
          <strong>{list.length}</strong> {list.length === 1 ? "paper" : "papers"} ·{" "}
          <strong>{decided}</strong> of <strong>{decls}</strong> declarations decided ·{" "}
          <strong>{found}</strong> confirmed {found === 1 ? "finding" : "findings"}
          {me && (
            <>
              {" "}
              · your part: <strong>{me.history.length}</strong>{" "}
              {me.history.length === 1 ? "review" : "reviews"}
            </>
          )}
        </p>
      </section>
      {stats && <Activity stats={stats} />}
      {list.length === 0 && <p className="muted">No paper has been submitted yet.</p>}
      {list.map((s) => (
        <section key={s.submission_id} className="card progress-card">
          <div className="progress-card-head">
            <h3>
              <a href={progressHref(s.submission_id)}>{s.title}</a>
            </h3>
            <PrlBadge s={s} />
            {s.closed && <span className="badge">closed</span>}
          </div>
          {s.main_statement && (
            <p className="progress-statement">
              <MathText text={s.main_statement} />
            </p>
          )}
          <div className="progress-grid">
            <div>
              <div className="hero-figure">{pct(s.coverage)}</div>
              <p className="muted small">
                of class-A declarations decided ({s.decided} of {s.declarations})
              </p>
              <StatusBar s={s} />
            </div>
            <Facts s={s} />
          </div>
          <p className="small">
            <a href={progressHref(s.submission_id)}>Details, history and notes →</a>
          </p>
        </section>
      ))}
      <section className="card">
        <h3>What is counted</h3>
        <p className="muted small">
          Counts are declarations, the units of review. A declaration counts as decided only when
          every review task about it is decided, so nothing here tells a reviewer which of their
          tasks is a planted error. Open work shows no verdicts: nobody sees how others voted before
          giving their own. The formal statement of a main theorem appears once it is decided and
          the planted errors of its paper are revealed; until then, the paper's statement is shown.
        </p>
        {stats?.audit_head && (
          <p className="muted small">
            Every figure is derived from the public audit log. Its current head:{" "}
            <code>{stats.audit_head.slice(0, 16)}</code>
          </p>
        )}
      </section>
    </div>
  );
}

// Activity of the whole community (formerly the statistics page). Aggregates
// only (SR-23), and no ticket counts.
function Activity({ stats }: { stats: Stats }) {
  const groups = Object.entries(stats.reviewers_by_group)
    .map(([g, n]) => `${n} ${g}`)
    .join(", ");
  const items: [string, number, string?][] = [
    ["reviewers", stats.reviewers, groups ? `By group: ${groups}` : undefined],
    ["reviews in the last 7 days", stats.reviews_last_7_days],
    ["reviews in progress", stats.active_leases],
    ["open claims", stats.open_claims, "Verdicts of an error, waiting for a re-check (PVV)"],
    [
      "planted errors revealed",
      stats.planted_errors_revealed,
      "Planted errors measure how reliable every reviewer is. They are revealed days later, in batches.",
    ],
  ];
  return (
    <section className="activity" aria-label="Activity">
      <span className="eyebrow">Activity</span>
      <ul>
        {items.map(([label, n, hint]) => (
          <li key={label} title={hint}>
            <strong>{n}</strong>
            <span>{label}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Ladder({ prl }: { prl: number }) {
  return (
    <ol className="prl-ladder">
      {PRL.map(([level, name, meaning]) => (
        <li
          key={level}
          className={level < prl ? "done" : level === prl ? "current" : undefined}
          aria-current={level === prl ? "step" : undefined}
        >
          <span className="prl-level">{level}</span>
          <span>
            <strong>{name}</strong>
            <span className="muted small">{meaning}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

function Units({
  units,
  sid,
  maintainer,
}: {
  units: ProgressUnit[];
  sid: string;
  maintainer: boolean;
}) {
  const [filter, setFilter] = useState<string>("all");
  const [all, setAll] = useState(false);
  const shown = units.filter((u) => filter === "all" || u.state === filter);
  const page = all ? shown : shown.slice(0, 50);
  return (
    <>
      <div className="chip-row" role="group" aria-label="Filter by state">
        {["all", ...STATES.map((s) => s.key)].map((f) => (
          <button key={f} className="chip" aria-pressed={filter === f} onClick={() => setFilter(f)}>
            {f === "all" ? `all ${units.length}` : STATES.find((s) => s.key === f)?.label}
          </button>
        ))}
      </div>
      <table className="units">
        <thead>
          <tr>
            <th>Declaration</th>
            <th>Kind</th>
            <th>Tier</th>
            <th>Domain</th>
            <th>State</th>
            <th>
              <span className="sr-only">Discussion</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {page.map((u) => (
            <tr key={u.declaration}>
              <td>
                {maintainer ? (
                  <a
                    href={`${progressHref(sid)}/${encodeURIComponent(u.declaration)}`}
                    title="Open the ticket as its reviewers see it (maintainers only)"
                  >
                    <code>{u.declaration}</code>
                  </a>
                ) : (
                  <code>{u.declaration}</code>
                )}
              </td>
              <td>{u.decl_kind}</td>
              <td>
                <TierBadge tier={u.tier} />
              </td>
              <td>{u.domain}</td>
              <td>
                <span className="state">
                  <span className={`swatch ${stateClass(u.state)}`} aria-hidden="true" />
                  <span aria-hidden="true">{STATES.find((s) => s.key === u.state)?.icon}</span>
                  {STATES.find((s) => s.key === u.state)?.label}
                </span>
              </td>
              <td>{u.discussion && <a href={threadHref(sid, u.declaration)}>Discussion →</a>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {shown.length > page.length && (
        <p>
          <button className="link small" onClick={() => setAll(true)}>
            Show all {shown.length}
          </button>
        </p>
      )}
    </>
  );
}

export function ProgressDetailView({ sid, me }: { sid: string; me: Me | null }) {
  const [d, setD] = useState<ProgressDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [named, setNamed] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(() => {
    api.progressDetail(sid).then(setD, (e) => setError((e as Error).message));
  }, [sid]);
  useEffect(load, [load]);

  if (error) return <p className="error">{error}</p>;
  if (!d) return <p className="muted">Loading…</p>;
  return (
    <div className="progress-page">
      <section className="card">
        <p className="small">
          <a href="#/progress">← All papers</a>
        </p>
        <div className="progress-card-head">
          <h2>{d.title}</h2>
          <PrlBadge s={d} />
          {d.closed && <span className="badge">closed</span>}
        </div>
        <p className="muted small">
          {d.paper_url && (
            <>
              <a href={d.paper_url}>the paper</a> ·{" "}
            </>
          )}
          <a href={d.repo_url}>{d.repo_url}</a> @ <code>{d.commit.slice(0, 12)}</code> · submitted{" "}
          {new Date(d.opened).toLocaleDateString("en", { dateStyle: "medium" })}
        </p>
        <div className="progress-grid">
          <div>
            <div className="hero-figure">{pct(d.coverage)}</div>
            <p className="muted small">
              of class-A declarations decided ({d.decided} of {d.declarations})
            </p>
            <StatusBar s={d} />
          </div>
          <Facts s={d} />
        </div>
      </section>

      <section className="card">
        <h3>The main statement</h3>
        {d.main_statement ? (
          <>
            <p className="eyebrow">The paper says{d.main_locator && ` · ${d.main_locator}`}</p>
            <p className="progress-statement">
              <MathText text={d.main_statement} />
            </p>
          </>
        ) : (
          <p className="muted">No passage of the paper is mapped to the main theorem yet.</p>
        )}
        {d.main_view ? (
          <details className="lean-details" open>
            <summary>
              Lean says: <code>{d.main_view.declaration}</code>
            </summary>
            <Infoview view={d.main_view} />
          </details>
        ) : (
          <p className="muted small">
            The formal statement
            {d.root && (
              <>
                {" "}
                of <code>{d.root}</code>
              </>
            )}{" "}
            is shown once it is decided and the planted errors of this paper are revealed, so that
            it cannot be compared with the copies under review.
          </p>
        )}
      </section>

      <Basis d={d} />

      <section className="card">
        <h3>Readiness level</h3>
        <p className="muted small">
          The proof readiness level (PRL) says how far a formal result can be trusted. A confirmed
          error in class A keeps it at level 1 until the formalization is fixed.
        </p>
        <Ladder prl={d.prl} />
      </section>

      <section className="card">
        <h3>Decided declarations over time</h3>
        <ProgressChart timeline={d.timeline} total={d.declarations} />
      </section>

      <section className="card">
        <h3>Declarations</h3>
        {me?.maintainer && (
          <p className="muted small">
            As a maintainer you can open each declaration and see the ticket as its reviewers do.
          </p>
        )}
        <Units units={d.units} sid={sid} maintainer={Boolean(me?.maintainer)} />
      </section>

      <section className="card">
        <h3>Notes by the maintainers</h3>
        <p className="muted small">
          Maintainers comment on the state of the review here. Signed-in reviewers can vote; votes
          only sort the notes and never change a decision.
        </p>
        {d.notes.map((p) => (
          <PostCard key={p.post_id} post={p} onChange={load} signedIn={me !== null} />
        ))}
        {d.notes.length === 0 && <p className="muted">No notes yet.</p>}
        {me?.maintainer && (
          <div className="note-composer">
            <label>
              New note
              <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} />
            </label>
            <label className="inline">
              <input type="checkbox" checked={named} onChange={(e) => setNamed(e.target.checked)} />
              Show my pseudonym
            </label>
            <p>
              <button
                disabled={!text.trim()}
                onClick={async () => {
                  setMessage(null);
                  try {
                    await api.note(sid, text, named);
                    setText("");
                    load();
                  } catch (e) {
                    setMessage((e as Error).message);
                  }
                }}
              >
                Publish note
              </button>
            </p>
            {message && <p className="error">{message}</p>}
          </div>
        )}
      </section>
    </div>
  );
}
