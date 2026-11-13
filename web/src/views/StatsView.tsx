import { Fragment, useEffect, useState } from "react";
import { api, type Stats } from "../api";

// Public aggregates only (SR-23).
export function StatsView() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [psi, setPsi] = useState<Record<string, number>>({});

  useEffect(() => {
    api.stats().then(setStats);
    api.attention().then(setPsi);
  }, []);

  if (!stats) return <p className="muted">Loading…</p>;
  return (
    <div className="columns">
      <section className="card narrow">
        <h2>Activity</h2>
        <dl className="kv">
          <dt>Reviewers</dt>
          <dd>{stats.reviewers}</dd>
          <dt>Submissions</dt>
          <dd>{stats.submissions}</dd>
          <dt>Reviews (7 days)</dt>
          <dd>{stats.reviews_last_7_days}</dd>
          <dt>Open claims</dt>
          <dd>{stats.open_claims}</dd>
          <dt>Tickets in work</dt>
          <dd>{stats.active_leases}</dd>
        </dl>
        <h3>Tickets</h3>
        <dl className="kv">
          {Object.entries(stats.tickets_by_status).map(([k, v]) => (
            <Fragment key={k}>
              <dt>{k === "honeypot" ? "planted errors (revealed)" : k}</dt>
              <dd>{v}</dd>
            </Fragment>
          ))}
        </dl>
        <p className="muted small">
          Audit log head: <code>{stats.audit_head?.slice(0, 16) ?? "—"}</code>
        </p>
      </section>
      <section className="card narrow">
        <h2>Interest per paper</h2>
        <p className="muted small">
          Estimated from binding choices (Plackett–Luce). It orders papers; it never decides whether
          class A is reviewed (SR-39).
        </p>
        {Object.keys(psi).length === 0 ? (
          <p className="muted">No completed choices yet.</p>
        ) : (
          <ul>
            {Object.entries(psi)
              .sort((a, b) => b[1] - a[1])
              .map(([paper, v]) => (
                <li key={paper}>
                  {paper}: <code>{v.toFixed(2)}</code>
                </li>
              ))}
          </ul>
        )}
      </section>
    </div>
  );
}
