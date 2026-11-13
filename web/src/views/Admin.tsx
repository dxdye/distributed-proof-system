import { useCallback, useEffect, useState } from "react";
import { api, type Escalated, type SubmissionRow } from "../api";

export function Admin() {
  const [subs, setSubs] = useState<SubmissionRow[]>([]);
  const [escalated, setEscalated] = useState<Escalated[]>([]);
  const [contested, setContested] = useState<
    { ticket_id: string; declaration: string; paper: string; locator: string; reasons: string[] }[]
  >([]);
  const [message, setMessage] = useState<string | null>(null);
  const [reasons, setReasons] = useState<Record<string, string>>({});

  const load = useCallback(() => {
    api.admin.submissions().then(setSubs);
    api.admin.escalated().then(setEscalated);
    api.admin.contested().then(setContested);
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
            onClick={() =>
              run(
                api.admin.tick,
                (r) => `${r.expired} leases expired, ${r.revealed} honeypots revealed`,
              )
            }
          >
            Run periodic tasks now
          </button>
        </div>
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
