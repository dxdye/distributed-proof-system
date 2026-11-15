import type { GlossaryEntry } from "../api";
import { Term } from "./Infoview";
import { MathText } from "./MathText";

// The front page for visitors who are not signed in: the problem, shown on a
// real formalization, and the goal. Figures and the glossary are
// those of the quasi-Riemann case study (docs/case-studies/quasi-riemann.md);
// the value of ζ at s = 1 is Mathlib's riemannZeta_one (Mathlib d13f23b7).
//
// Public examples show every reviewer what to look for in exactly that
// declaration. Only a declaration that is decided, with every planted error of
// its paper revealed, may appear here (proposal C-07).

const LEAN_LINE = "∀ {s : ℂ}, 7 / 8 < s.re → riemannZeta s ≠ 0";

const GLOSSARY: GlossaryEntry[] = [
  {
    name: "riemannZeta",
    type: "ℂ → ℂ",
    origin: "library",
    doc: "The Riemann zeta function ζ(s).",
    note: "Mathlib gives ζ a value at the pole s = 1: riemannZeta 1 = (γ − log(4π)) / 2 (lemma riemannZeta_one).",
  },
  {
    name: "Complex.re",
    type: "ℂ → ℝ",
    origin: "library",
    doc: "The real part of a complex number.",
  },
  {
    name: "Complex",
    type: "Type",
    origin: "library",
    doc: "Complex numbers consist of two Reals: a real part re and an imaginary part im.",
  },
  {
    name: "Real",
    type: "Type",
    origin: "library",
    doc: "The type ℝ of real numbers constructed as equivalence classes of Cauchy sequences of rational numbers.",
  },
  { name: "Nat", type: "Type", origin: "core", doc: "The natural numbers, starting at zero." },
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
          <p className="example-label">Example: a claimed result on the Riemann zeta function</p>
          <p>
            A formalization in the repository <span className="mono">openai/math</span>, which lists
            it as unchecked, proves the theorem below. If the line says what it seems to say, it is
            a major result: no zeros of <MathText text="$\zeta$" /> in a half-plane{" "}
            <MathText text="$\operatorname{Re}(s) > \sigma$" /> with{" "}
            <MathText text="$\sigma < 1$" /> is an open problem. Whether it does comes down to one
            line.
          </p>
          <div className="claim-pair">
            <div>
              <p className="term-label">What the paper claims</p>
              <div className="example-formula">
                <MathText text="$$\forall s \in \mathbb{C},\quad \frac{7}{8} < \operatorname{Re}(s) \implies \zeta(s) \neq 0$$" />
              </div>
            </div>
            <div>
              <p className="term-label">What Lean proves</p>
              <Term text={LEAN_LINE} glossary={GLOSSARY} />
              <p className="small muted">
                <span className="mono">OAI.riemannZeta_ne_zero_of_seven_eighths_lt_re</span>. Point
                at a name to see its type, as a reviewer does.
              </p>
            </div>
          </div>
          <p>
            Lean's kernel has checked the proof: {"53 394"} declarations, none rejected. It cannot
            check the line itself. A few ways the line could be wrong while every proof still
            checks:
          </p>
          <ul className="example-risks">
            <li>
              <MathText text="$\operatorname{Re}(s) > 1$ instead of $\operatorname{Re}(s) > 7/8$" />
              : a classical theorem, true and provable, but not what the paper claims.
            </li>
            <li>
              A function that looks like <MathText text="$\zeta$" /> but is defined differently.
            </li>
            <li>
              The line also covers <MathText text="$s = 1$" />, where <MathText text="$\zeta$" />{" "}
              has a pole. Mathlib gives <MathText text="$\zeta$" /> a fixed value there,{" "}
              <MathText text="$(\gamma - \log 4\pi)/2 \approx -0.98$" /> (
              <span className="mono">riemannZeta_one</span>), and that value is not 0. Harmless
              here, but someone has to notice it and decide.
            </li>
          </ul>
          <p className="small muted">
            Formalizations of larger problems, such as Navier–Stokes, depend on several definitions
            in the same way: one condition too few in the definition of a "smooth solution", and the
            theorem is about something else.
          </p>
        </div>
      </section>

      <section className="card intro-goal">
        <span className="eyebrow">The goal</span>
        <h2>Review what matters, and measure how well it was reviewed.</h2>
        <p>
          The system takes a formalization apart automatically. Only the statement and the
          definitions it depends on need human judgement; for the example above that is one line,
          against {"53 394"} declarations the kernel had to check. Volunteers review them under a
          pseudonym, comparing each with the paper. Errors planted on purpose measure how reliable
          every reviewer is, so that the result is not a show of hands but a figure: how likely it
          is that an error went unnoticed. Every report is published, including negative ones.
        </p>
        <p className="intro-links">
          <a href="#/how">How a review works →</a>
          <a href="#/progress">Where every paper stands →</a>
        </p>
      </section>
    </>
  );
}
