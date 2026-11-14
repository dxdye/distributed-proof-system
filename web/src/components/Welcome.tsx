import { useState } from "react";
import type { Me } from "../api";

// First steps for a new reviewer (OS-2, light version for the pilot): what a
// review is, before the first ticket. Shown until the first verdict is in or it
// is put away; it can be opened again from the work page.

const key = (rid: string) => `dpc.intro-done.${rid}`;

export function introDone(me: Me): boolean {
  try {
    return me.history.length > 0 || localStorage.getItem(key(me.reviewer_id)) === "1";
  } catch {
    return me.history.length > 0;
  }
}

const STEPS: [string, string][] = [
  [
    "Pick a ticket you can judge.",
    "You are offered a few tickets from different papers. Choose one from a field you know; the choice is binding until you submit or return it, and returning carries no penalty.",
  ],
  [
    "Compare the paper with what Lean says.",
    "A ticket is one statement or definition. The kernel has checked the proof; you check the meaning: does the formal statement say what the paper says, no more and no less?",
  ],
  [
    "Mind the words it takes from Mathlib.",
    "Under the statement the ticket lists the library definitions it relies on, with the conventions to know, such as the value a function takes where mathematics leaves it undefined.",
  ],
  [
    "Answer the five questions.",
    "If one fails, say which and why: a found problem needs a justification, and a Lean file as evidence helps. When nothing fails, a reason is optional.",
  ],
  [
    "Expect planted errors, and patience.",
    "Some tickets carry an error put there on purpose; nobody can tell which while they are open. They are revealed days later and measure how reliable each review is. Until then your verdicts carry no weight: that is how every account starts.",
  ],
];

export function Welcome({ me, onClose }: { me: Me; onClose: () => void }) {
  const [open, setOpen] = useState(true);
  if (!open) return null;
  function close() {
    try {
      localStorage.setItem(key(me.reviewer_id), "1");
    } catch {
      /* storage blocked: the card comes back next time */
    }
    setOpen(false);
    onClose();
  }
  return (
    <section className="card welcome" aria-labelledby="welcome-title">
      <span className="eyebrow">First steps</span>
      <h2 id="welcome-title">How a review goes</h2>
      <ol className="welcome-steps">
        {STEPS.map(([title, text]) => (
          <li key={title}>
            <strong>{title}</strong>
            <p>{text}</p>
          </li>
        ))}
      </ol>
      <p className="muted small">
        There is no clock: take the time a ticket needs. If you use an AI assistant, say so in the
        review.
      </p>
      <div className="row welcome-actions">
        <button onClick={close}>Got it, show me tickets</button>
        <a href="#/how">More on how it works →</a>
      </div>
    </section>
  );
}
