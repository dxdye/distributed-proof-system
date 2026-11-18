import type { Me } from "../api";
import { LeanName } from "../components/LeanName";

// Own reviews. Planted errors (honeypots) are revealed only later and in batches
// (SR-37); until then the column stays empty.
export function History({ me }: { me: Me }) {
  return (
    <section className="card">
      <h2>Your reviews</h2>
      {me.history.length === 0 ? (
        <p className="muted">No reviews yet.</p>
      ) : (
        <table className="history">
          <thead>
            <tr>
              <th>Declaration</th>
              <th>Paper</th>
              <th>Your verdict</th>
              <th>Outcome</th>
              <th>Planted error?</th>
            </tr>
          </thead>
          <tbody>
            {me.history.map((h, i) => (
              <tr key={i}>
                <td>
                  <LeanName text={h.declaration} /> {h.duty !== "review" && <span className="badge">{h.duty}</span>}
                </td>
                <td>{h.paper}</td>
                <td>{h.verdict}</td>
                <td>{h.outcome ?? <span className="muted">open</span>}</td>
                <td>
                  {h.planted_error === null ? (
                    <span className="muted">not yet revealed</span>
                  ) : h.planted_error ? (
                    h.verdict === "incorrect" ? "yes — you found it" : "yes — missed"
                  ) : (
                    "no"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3>Your roles</h3>
      {Object.keys(me.roles).length === 0 ? (
        <p className="muted small">
          Roles (PV, PVV) are earned per domain from planted errors found and from confirmed
          findings.
        </p>
      ) : (
        <ul>
          {Object.entries(me.roles).map(([domain, roles]) => (
            <li key={domain}>
              {domain}: {roles.length ? roles.join(", ") : <span className="muted">none yet</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
