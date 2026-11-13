import { useCallback, useEffect, useState } from "react";
import { api, type Escalated, type SubmissionRow } from "../api";
import { threadHref } from "./Discussions";

export function Admin() {
  const [subs, setSubs] = useState<SubmissionRow[]>([]);
  const [escalated, setEscalated] = useState<Escalated[]>([]);
  const [contested, setContested] = useState<
    { ticket_id: string; declaration: string; paper: string; locator: string; reasons: string[] }[]
  >([]);
  const [message, setMessage] = useState<string | null>(null);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [reports, setReports] = useState<
    {
      post_id: string;
      submission_id: string;
      declaration: string;
      text: string;
      kind: string;
      reasons: string[];
    }[]
  >([]);
  const [reopens, setReopens] = useState<
    {
      request_id: string;
      declaration: string;
      paper: string;
      submission_id: string;
      outcome: string;
      reason: string;
    }[]
  >([]);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const load = useCallback(() => {
    api.admin.submissions().then(setSubs);
    api.admin.escalated().then(setEscalated);
    api.admin.contested().then(setContested);
    api.admin.reports().then(setReports);
    api.admin.reopens().then(setReopens);
  }, []);
  useEffect(load, [load]);

  async function run<T>(action: () => Promise<T>, done: (r: T) => string) {
    try {
      setMessage(done(await action()));
      load();
    } catch (e) {
      setMessage((e as Error).message);
    }
  }

  return (
    <div>
      <section className="card">
        <div className="row">
          <h2>Submissions</h2>
          <button
            className="secondary"
            title="End leases whose time ran out and reveal planted errors that are due, now instead of at the next minute"
            onClick={() =>
              run(
                api.admin.tick,
                (r) => `${r.expired} leases expired, ${r.revealed} honeypots revealed`,
              )
            }
          >
            Run scheduled tasks now
          </button>
        </div>
        <p className="muted small">
          Every minute the service ends leases whose time has run out (this lowers the reliability
          of whoever let them lapse) and reveals planted errors whose waiting time is over, in
          batches. "Run scheduled tasks now" does this immediately instead of at the next minute.
        </p>
        {message && <p className="muted">{message}</p>}
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Commit</th>
              <th>Tickets</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {subs.map((s) => (
              <tr key={s.submission_id}>
                <td>{s.title}</td>
                <td>
                  <code>{s.commit.slice(0, 12)}</code>
                </td>
                <td className="small">
                  {Object.entries(s.tickets)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(" · ")}
                </td>
                <td>
                  {s.closed ? (
                    <span className="muted">closed</span>
                  ) : (
                    <button
                      className="secondary"
                      onClick={() =>
                        window.confirm(`Close ${s.title} and open all commitments?`) &&
                        run(
                          () => api.admin.close(s.submission_id),
                          () => "closed",
                        )
                      }
                    >
                      Close
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="card">
        <h2>Escalated tickets</h2>
        {escalated.length === 0 && <p className="muted">None.</p>}
        {escalated.map((t) => (
          <div key={t.ticket_id} className="escalated">
            <p>
              <code>{t.declaration}</code> <span className="muted">{t.paper}</span>
            </p>
            <ul className="small">
              {t.votes.map((v, i) => (
                <li key={i}>
                  {v.verdict} {v.reason && <span className="muted">— {v.reason}</span>}
                </li>
              ))}
            </ul>
            <textarea
              rows={2}
              placeholder="Justification"
              value={reasons[t.ticket_id] ?? ""}
              onChange={(e) => setReasons({ ...reasons, [t.ticket_id]: e.target.value })}
            />
            <div className="row">
              {[false, true].map((error) => (
                <button
                  key={String(error)}
                  className={error ? "secondary" : ""}
                  disabled={!reasons[t.ticket_id]?.trim()}
                  onClick={() =>
                    run(
                      () => api.admin.decide(t.ticket_id, error, reasons[t.ticket_id]),
                      () => "decided",
                    )
                  }
                >
                  {error ? "Erroneous" : "Accept"}
                </button>
              ))}
            </div>
          </div>
        ))}
      </section>
      <section className="card">
        <h2>Reopen requests</h2>
        <p className="muted small">
          Someone in a discussion says a decided declaration is wrong after all. Reopening turns it
          into an escalation, decided like any other; discussion never decides by itself.
        </p>
        {reopens.length === 0 ? (
          <p className="muted">No open request.</p>
        ) : (
          reopens.map((q) => (
            <div key={q.request_id} className="escalated">
              <p>
                <a href={threadHref(q.submission_id, q.declaration)}>
                  <code>{q.declaration}</code>
                </a>{" "}
                <span className="muted small">
                  {q.paper} · decided: {q.outcome}
                </span>
              </p>
              <blockquote>{q.reason}</blockquote>
              <textarea
                rows={2}
                placeholder="Your reason"
                value={notes[q.request_id] ?? ""}
                onChange={(e) => setNotes({ ...notes, [q.request_id]: e.target.value })}
              />
              <div className="toolbar">
                <button
                  disabled={!(notes[q.request_id] ?? "").trim()}
                  onClick={() =>
                    run(
                      () => api.admin.resolveReopen(q.request_id, true, notes[q.request_id]),
                      () => "Reopened: the ticket is now escalated.",
                    )
                  }
                >
                  Reopen as escalation
                </button>
                <button
                  className="secondary"
                  disabled={!(notes[q.request_id] ?? "").trim()}
                  onClick={() =>
                    run(
                      () => api.admin.resolveReopen(q.request_id, false, notes[q.request_id]),
                      () => "Request dismissed.",
                    )
                  }
                >
                  Dismiss
                </button>
              </div>
            </div>
          ))
        )}
      </section>
      <section className="card">
        <h2>Reported posts</h2>
        {reports.length === 0 ? (
          <p className="muted">No reported post.</p>
        ) : (
          reports.map((r) => (
            <div key={r.post_id} className="escalated">
              <p>
                <a href={threadHref(r.submission_id, r.declaration)}>
                  <code>{r.declaration}</code>
                </a>
              </p>
              <blockquote>{r.text || `(${r.kind})`}</blockquote>
              <p className="small muted">Reported because: {r.reasons.join(" · ")}</p>
              <div className="toolbar">
                <input
                  placeholder="Reason for hiding"
                  value={notes[r.post_id] ?? ""}
                  onChange={(e) => setNotes({ ...notes, [r.post_id]: e.target.value })}
                />
                <button
                  className="secondary"
                  disabled={!(notes[r.post_id] ?? "").trim()}
                  onClick={() =>
                    run(
                      () => api.admin.hide(r.post_id, notes[r.post_id]),
                      () => "Post hidden.",
                    )
                  }
                >
                  Hide post
                </button>
              </div>
            </div>
          ))
        )}
      </section>
      <section className="card">
        <h2>Contested paper mappings</h2>
        {contested.length === 0 ? (
          <p className="muted">No reviewer has contested a mapping.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Declaration</th>
                <th>Paper and passage</th>
                <th>Reasons</th>
              </tr>
            </thead>
            <tbody>
              {contested.map((c) => (
                <tr key={c.ticket_id}>
                  <td>
                    <code>{c.declaration}</code>
                  </td>
                  <td className="small">
                    {c.paper} · {c.locator}
                  </td>
                  <td className="small">
                    {c.reasons.map((r, i) => (
                      <p key={i}>{r}</p>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
