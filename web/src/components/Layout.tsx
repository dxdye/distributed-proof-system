import { useState } from "react";
import { getTheme, setTheme, type ThemeChoice } from "../theme";

// Page frame: brand mark, colour-scheme switch, footer.

/** The mark: ⊢, "is provable", in a square. Own design, no official insignia. */
export function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="6" fill="var(--mark-bg)" />
      <path
        d="M10 8v16M10 16h12"
        stroke="var(--mark-ink)"
        strokeWidth="3"
        strokeLinecap="square"
        fill="none"
      />
    </svg>
  );
}

const CHOICES: { value: ThemeChoice; label: string }[] = [
  { value: "system", label: "Auto" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

export function ThemeSwitch() {
  const [choice, setChoice] = useState<ThemeChoice>(getTheme);
  return (
    <div className="theme-switch" role="group" aria-label="Colour scheme">
      {CHOICES.map((c) => (
        <button
          key={c.value}
          aria-pressed={choice === c.value}
          title={c.value === "system" ? "Follow the system setting" : `${c.label} mode`}
          onClick={() => {
            setTheme(c.value);
            setChoice(c.value);
          }}
        >
          {c.label}
        </button>
      ))}
    </div>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="container footer-grid">
        <div>
          <div className="footer-brand">Distributed Proof Check</div>
          <p>
            Human review of machine-checked mathematics: does a formal proof state what the paper
            claims? Reviews are pseudonymous and published openly with every report.
          </p>
        </div>
        <div>
          <h4>Service</h4>
          <ul>
            <li>
              <a href="#/work">Review</a>
            </li>
            <li>
              <a href="#/progress">Progress</a>
            </li>
            <li>
              <a href="#/how">How it works</a>
            </li>
          </ul>
        </div>
        <div>
          <h4>Legal</h4>
          <ul>
            <li>
              <a href="#/imprint">Imprint · Impressum</a>
            </li>
            <li>
              <a href="#/privacy">Privacy · Datenschutz</a>
            </li>
          </ul>
        </div>
      </div>
      <div className="footer-bottom">
        <div className="container footer-bottom-row">
          <span>
            Research prototype. Lean 4 proofs are checked by the Lean kernel; statements are
            reviewed by people.
          </span>
          <span className="appearance">
            Appearance <ThemeSwitch />
          </span>
        </div>
      </div>
    </footer>
  );
}
