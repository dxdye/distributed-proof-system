import type { GlossaryEntry } from "../api";
import { Term } from "./Infoview";
import { MathText } from "./MathText";

// The front page for visitors who are not signed in: the problem, shown on a
// real formalization, and the goal. The example is the Navier–Stokes case
// study (docs/case-studies/navier-stokes.md): the regularity condition of its
// definition of a smooth solution, and the glossary as the ticket shows it.
// The convention on ⊤ is Mathlib's (Analysis/Calculus/ContDiff/Defs.lean,
// checked in the Mathlib versions of both case studies).
//
// Public examples show every reviewer what to look for in exactly that
// declaration. Only a declaration that is decided, with every planted error of
// its paper revealed, may appear here (proposal C-07). In the test system the
// Navier–Stokes paper is not fully decided yet: it must be before any launch.

const LEAN_LINES =
  "ContDiffOn ℝ (↑⊤) (↿v) (Set.univ ×ˢ Set.Ici 0) →\n" +
  "  ContDiffOn ℝ (↑⊤) (↿p) (Set.univ ×ˢ Set.Ici 0) →";

const GLOSSARY: GlossaryEntry[] = [
  {
    name: "ContDiffOn",
    type: "(𝕜 : Type u) → … → WithTop ℕ∞ → (E → F) → Set E → Prop",
    origin: "library",
    doc: "A function is continuously differentiable up to n on s if, for any point x in s, it admits continuous derivatives up to order n on a neighborhood of x in s. The parameter n can be a natural number, ∞, or ω.",
    note: "The order n lies in WithTop ℕ∞: ∞ = ↑(⊤ : ℕ∞) means smooth (contDiff_infty), ω = ⊤ means analytic (Mathlib.Analysis.Calculus.ContDiff.Defs). A bare ⊤ here is ω, not ∞.",
  },
  {
    name: "Set.univ",
    type: "{α : Type u} → Set α",
    origin: "library",
    doc: "The universal set on a type α is the set containing all elements of α.",
  },
  {
    name: "Set.Ici",
    type: "{α : Type u_1} → [Preorder α] → α → Set α",
    origin: "library",
    doc: "Ici a is the left-closed right-infinite interval [a, ∞).",
  },
];

export function Intro() {
  return (
    <>
      <section className="card intro-problem">
        <span className="eyebrow">The problem</span>
        <h2>A proof can be correct and still prove the wrong thing.</h2>
        <p>
          AI systems now produce formal proofs at scale, faster than anyone can read them. This is
          what the gap looks like in a real case.
        </p>
        <div className="example">
          <p className="example-label">Example: a claimed answer to the Navier–Stokes problem</p>
          <p>
            A formalization published by OpenAI (
            <span className="mono">openai/NavierStokesAndEuler</span>) proves a breakdown: for every
            viscosity <MathText text="$\nu > 0$" /> there are smooth, rapidly decaying initial data
            and forces on <MathText text="$\mathbb{R}^3$" /> for which no smooth solution exists. If
            it says what it seems to say, it settles a Millennium Prize problem. Whether it does
            depends on eight declarations, 116 lines: what counts as smooth data, a smooth force, a
            smooth solution.
          </p>
          <div className="claim-pair">
            <div>
              <p className="term-label">What the problem asks</p>
              <div className="example-formula">
                <MathText text="$$u,\ p \in C^\infty\big(\mathbb{R}^3 \times [0, \infty)\big)$$" />
              </div>
              <p className="small muted">
                Fefferman's official statement, condition (6): the solution is smooth.
              </p>
            </div>
            <div>
              <p className="term-label">What Lean says</p>
              <Term text={LEAN_LINES} glossary={GLOSSARY} />
              <p className="small muted">
                The last two conditions of{" "}
                <span className="mono">
                  NavierStokes.Comparator.NavierStokesExistenceAndSmoothness
                </span>
                . Point at a name to see its type, as a reviewer does.
              </p>
            </div>
          </div>
          <p>
            In Mathlib, <MathText text="$\uparrow\!\top$" /> means <MathText text="$C^\infty$" />.
            Without the arrow, <MathText text="$\top$" /> means <MathText text="$C^\omega$" />,
            analytic. The theorem would then only say that no analytic solution exists, a much
            weaker claim, and every proof would still check. One arrow decides whether this is the
            Millennium problem. This formalization writes <MathText text="$\uparrow\!\top$" />.
          </p>
          <p>Other things a reviewer of this paper has to check:</p>
          <ul className="example-risks">
            <li>
              The force: smooth and decaying on all of{" "}
              <MathText text="$\mathbb{R}^3 \times [0, \infty)$" />? A force that is smooth only for{" "}
              <MathText text="$t > 0$" />, or grows without bound, can make the breakdown trivial.
            </li>
            <li>
              The energy: <MathText text="$\int |u(x,t)|^2\,dx$" /> bounded for all{" "}
              <MathText text="$t \ge 0$" />, exactly as in the problem?
            </li>
            <li>
              The breakdown itself: does the theorem say that no smooth solution exists, and not
              merely that some solution becomes singular?
            </li>
          </ul>
          <p className="small muted">
            At the other extreme, a formalization claiming <MathText text="$\zeta(s) \neq 0$" /> for{" "}
            <MathText text="$\operatorname{Re}(s) > 7/8$" /> (
            <span className="mono">openai/math</span>) comes down to a single line, and everything
            that line means lies in Mathlib's definitions.
          </p>
        </div>
      </section>

      <section className="card intro-goal">
        <span className="eyebrow">The goal</span>
        <h2>Review what matters, and measure how well it was reviewed.</h2>
        <p>
          The system takes a formalization apart automatically. Only the statement and the
          definitions it depends on need human judgement; for the example above that is eight
          declarations, against {"23 820"} parts of the proof that only the kernel needs to see.
          Volunteers review them under a pseudonym, comparing each with the paper. Errors planted on
          purpose measure how reliable every reviewer is, so that the result is not a show of hands
          but a figure: how likely it is that an error went unnoticed. Every report is published,
          including negative ones.
        </p>
        <p className="intro-links">
          <a href="#/how">How a review works →</a>
          <a href="#/progress">Where every paper stands →</a>
        </p>
      </section>
    </>
  );
}
