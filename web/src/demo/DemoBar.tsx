import { currentRole, resetDemo, ROLES, switchRole, type Role } from "./mock";

// Banner of the click dummy and its sign-in: instead of signing in, you choose
// the role you want to see the platform from.

export function DemoBar() {
  return (
    <>
      <div className="demo-bar" role="region" aria-label="Click dummy">
        <div className="container demo-inner">
          <span>
            <strong>Click dummy.</strong> Simulated data in your browser; nothing is sent or stored.
            Planted errors are revealed right after your verdict (in the real system: days later).
          </span>
          <span className="demo-roles">
            <a href="#/choose-role">{currentRole() ? "Switch role" : "Choose a role"}</a>
            <button className="link" onClick={resetDemo} title="Start over with the seeded data">
              Reset
            </button>
          </span>
        </div>
      </div>
      <div className="test-sash" aria-hidden="true">
        <span>Test</span>
      </div>
    </>
  );
}

const TAGLINE: Record<Role, string> = {
  newcomer: "Just joined.",
  pv: "A reviewer with earned trust.",
  pvv: "Checks the checkers.",
  maintainer: "Looks after the content of a domain.",
  root: "Test systems only: everything at once.",
};

const CAN: Record<Role, string[]> = {
  newcomer: [
    "Easy and medium tickets, one at a time",
    "Your verdicts carry little weight until planted errors have measured you",
    "Join discussions once a declaration is decided",
  ],
  pv: [
    "Hard tickets open: trust earned in the domain",
    "Two tickets at a time",
    "Share your reviews in the discussion",
  ],
  pvv: [
    "Every tier, including excellence",
    "Re-checks: decide claimed errors, check verdicts of others again",
    "Three tickets at a time",
  ],
  maintainer: [
    "Escalations, contested paper passages, reopen requests in the domain",
    "Notes on the progress page, hashtags, moderation",
    "Sees originals under review, and therefore does not review them",
  ],
  root: [
    "Every role at once: reviewer, PVV, maintainer, administrator",
    "Free of the rules: no limits, every tier, every page",
    "Exists only in test systems and in this dummy, never in production",
  ],
};

export function ChooseRole() {
  const role = currentRole();
  return (
    <>
      <section className="hero">
        <span className="eyebrow">Click dummy · sign-in</span>
        <h1>Choose your role</h1>
        <p className="lead">
          There is no real sign-in here. Pick the role you want to see the platform from; you can
          switch at any time with “Switch role” in the bar at the top.
        </p>
      </section>
      <div className="role-grid">
        {ROLES.map((r) => (
          <section key={r.role} className="card role-card">
            <h2>{r.label}</h2>
            <p className="muted">{TAGLINE[r.role]}</p>
            <ul className="checklist">
              {CAN[r.role].map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
            <button
              className={role === r.role ? "secondary" : undefined}
              aria-label={`Continue as ${r.label}`}
              onClick={() => switchRole(r.role)}
            >
              {role === r.role ? "Your current role" : "Continue"}
            </button>
          </section>
        ))}
      </div>
    </>
  );
}
