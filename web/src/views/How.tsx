import { MathText } from "../components/MathText";

// How it works: what a ticket is, how verdicts are weighed, the rules that
// protect the review, and where to learn to read Lean (SR-49 in part; the
// pilot needs this page). It says *that* errors are planted and why, never
// what they look like.

const QUESTIONS: { title: string; text: string; example: string }[] = [
  {
    title: "Does it say what the paper says?",
    text: "No more, no less: the same objects, the same hypotheses, the same conclusion.",
    example:
      "The paper claims $\\zeta(s) \\neq 0$ for $\\operatorname{Re} s > 7/8$; a formal statement for $\\operatorname{Re} s > 1$ is true, but a different theorem.",
  },
  {
    title: "Junk values",
    text: "Lean makes functions total by fixing values where mathematics leaves them undefined. A statement can then hold for the wrong reason.",
    example:
      "In Lean $x / 0 = 0$, on natural numbers $3 - 5 = 0$ and $7 / 8 = 0$, and Mathlib gives $\\zeta$ a value at the pole $s = 1$.",
  },
  {
    title: "Edge cases",
    text: "Empty sets, zero, dimension 0 or 1: are they treated as in the paper?",
    example:
      "A bound stated for all $n \\in \\mathbb{N}$ includes $n = 0$, even if the paper starts at $n = 1$.",
  },
  {
    title: "Can the hypotheses hold?",
    text: "If they contradict each other, the statement is vacuously true and says nothing.",
    example: "$\\forall n,\\ 2 \\le n \\implies n < 2 \\implies P(n)$ is provable for every $P$.",
  },
  {
    title: "Quantifiers and types",
    text: "Order of $\\forall$ and $\\exists$, and the types of bound variables.",
    example:
      "$\\forall n\\, \\exists m,\\ n < m$ is true; $\\exists m\\, \\forall n,\\ n < m$ is false.",
  },
];

export function How() {
  return (
    <div className="how">
      <section className="hero">
        <span className="eyebrow">How it works</span>
        <h1>Reviewing a formal statement</h1>
        <p className="lead">
          A machine checks every proof. People check what is proven: whether the formal statement
          says what the paper claims. This page explains how a review works here and why the rules
          are the way they are.
        </p>
      </section>

      <section className="card">
        <h2>What a ticket is</h2>
        <p>
          A ticket is one declaration of a formalization: the main theorem, or a definition it
          depends on. You see three things:
        </p>
        <ul>
          <li>
            <b>The paper</b>: the informal statement it should formalize, with its place in the
            paper. If you think the passage does not belong to the declaration, say so; mappings can
            be contested.
          </li>
          <li>
            <b>The formula</b>: the Lean term typeset, with types and coercions visible.
          </li>
          <li>
            <b>The Lean text</b>: the binding version. Hover over a name to see its type, where it
            comes from (Lean, Mathlib or the submission) and known junk values.
          </li>
        </ul>
        <p>
          Proofs are not your concern: the Lean kernel has checked them, and checks them again
          before review. Your concern is meaning.
        </p>
      </section>

      <section className="card">
        <h2>The five questions</h2>
        <p className="muted">
          Every ticket asks the same five questions. A verdict "incorrect" names the one that fails.
        </p>
        <ol className="how-questions">
          {QUESTIONS.map((q) => (
            <li key={q.title}>
              <strong>{q.title}</strong>
              <p>
                <MathText text={q.text} />
              </p>
              <p className="small muted">
                Example: <MathText text={q.example} />
              </p>
            </li>
          ))}
        </ol>
      </section>

      <div className="columns">
        <section className="card">
          <h2>Planted errors</h2>
          <p>
            Some tickets contain an error that was put there on purpose. They look exactly like real
            tickets. They are how the system learns how reliable each review is: agreement alone
            cannot tell careful reviewers from people who click "correct" every time.
          </p>
          <p>
            You learn which of your tickets had a planted error later, in batches, so that nobody
            can tell them apart while they are open. Finding one counts; missing one costs trust.
          </p>
        </section>
        <section className="card">
          <h2>Trust and roles</h2>
          <p>
            Your verdicts count as far as your measured reliability in a domain goes: planted errors
            found, re-checks passed, confirmed findings. New accounts start with no weight.
          </p>
          <ul>
            <li>
              <b>Reviewer (PV)</b>: reviews tickets; opens hard tickets in the domain.
            </li>
            <li>
              <b>Re-checker (PVV)</b>: re-checks samples of verdicts and decides claims; opens
              excellence tickets.
            </li>
            <li>
              <b>Maintainer</b>: decides escalations and releases reports; appointed, not earned.
            </li>
          </ul>
        </section>
      </div>

      <div className="columns">
        <section className="card">
          <h2>Taking tickets</h2>
          <ul>
            <li>You choose from a few tickets drawn at random from different papers.</li>
            <li>
              Your choice is binding, but you can return a ticket at any time without penalty.
            </li>
            <li>There is no countdown. Take the time a ticket needs.</li>
            <li>
              Preferences (domains, difficulty) make matching tickets more likely; they never let
              you pick a particular paper.
            </li>
          </ul>
        </section>
        <section className="card">
          <h2>Rules</h2>
          <ul>
            <li>
              <b>AI tools</b> may help you look things up, but the verdict and the justification
              must be your own, and AI use must be declared.
            </li>
            <li>
              <b>Conflicts of interest</b>: declare employment by or commissions from a lab whose
              submissions you might review; you will not get their tickets.
            </li>
            <li>
              <b>Openness</b>: reviews are published with the reports under an open licence, with a
              random id instead of your pseudonym, and may be used to train and evaluate AI systems.
            </li>
          </ul>
        </section>
      </div>

      <section className="card">
        <h2>Learning to read Lean</h2>
        <p>You need to read statements, not write proofs. Good places to start:</p>
        <ul>
          <li>
            <a href="https://adam.math.hhu.de/#/g/leanprover-community/nng4">Natural Number Game</a>{" "}
            — the basics, playfully.
          </li>
          <li>
            <a href="https://leanprover-community.github.io/mathematics_in_lean/">
              Mathematics in Lean
            </a>{" "}
            — how Mathlib states mathematics.
          </li>
          <li>
            <a href="https://lean-lang.org/theorem_proving_in_lean4/">Theorem Proving in Lean 4</a>{" "}
            — the language itself.
          </li>
          <li>
            <a href="https://live.lean-lang.org/">Lean 4 Web</a> — try statements and evidence files
            in the browser.
          </li>
        </ul>
      </section>
    </div>
  );
}
