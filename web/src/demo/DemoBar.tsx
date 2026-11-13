import { currentRole, resetDemo, ROLES, switchRole } from "./mock";

// Banner of the click dummy: what this is, and the role you are looking from.
export function DemoBar() {
  const role = currentRole();
  return (
    <div className="demo-bar" role="region" aria-label="Click dummy">
      <div className="container demo-inner">
        <span>
          <strong>Click dummy.</strong> Simulated data in your browser; nothing is sent or stored.
          Planted errors are revealed right after your verdict (in the real system: days later).
        </span>
        <span className="demo-roles">
          View as
          <span className="segmented">
            {ROLES.map((r) => (
              <button
                key={r.role}
                aria-pressed={role === r.role}
                title={r.hint}
                onClick={() => switchRole(r.role)}
              >
                {r.label}
              </button>
            ))}
          </span>
          <button className="link" onClick={resetDemo}>
            Reset
          </button>
        </span>
      </div>
    </div>
  );
}
