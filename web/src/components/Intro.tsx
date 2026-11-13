import { MathText } from "./MathText";

// The front page for visitors who are not signed in: the problem, an example
// from a real formalization, and the goal. Figures are those of the
// quasi-Riemann case study (docs/case-studies/quasi-riemann.md).

export function Intro() {
  return (
    <>
      <section className="card intro-problem">
        <span className="eyebrow">The problem</span>
        <h2>A proof can be correct and still prove the wrong thing.</h2>
        <p>
          AI systems now produce formal proofs at scale. A proof assistant like Lean checks every
          step of such a proof, so the proof itself can be trusted. What no machine checks is
          whether the statement that was proven is the one the paper claims.
        </p>
        <div className="example">
          <p className="example-label">Example: a result on the Riemann zeta function</p>
          <p>
            A formalization published in the repository <span className="mono">openai/math</span>{" "}
            proves a theorem that is a single line long:
          </p>
          <div className="example-formula">
            <MathText text="$$\forall s \in \mathbb{C},\quad \frac{7}{8} < \operatorname{Re}(s) \implies \zeta(s) \neq 0$$" />
          </div>
          <p>
            The Lean kernel has checked its proof: 53 394 declarations, none rejected. What remains
            is the one line itself. A few ways it could be wrong while every proof still checks:
          </p>
          <ul className="example-risks">
            <li>
              <MathText text="$\operatorname{Re}(s) > 1$ instead of $\operatorname{Re}(s) > 7/8$" />
              : a true, classical theorem, and provable — but not what the paper claims.
            </li>
            <li>
              Hypotheses that can never hold together: then <em>any</em> conclusion is provable, and
              the theorem says nothing.
            </li>
            <li>
              A function that looks like <MathText text="$\zeta$" /> but is defined differently, or
              a convention such as Mathlib's value of <MathText text="$\zeta$" /> at its pole{" "}
              <MathText text="$s = 1$" />.
            </li>
          </ul>
          <p className="small muted">
            Formalizations of larger results, such as the Navier–Stokes problem, depend on several
            definitions in the same way: one condition too few in the definition of a "smooth
            solution", and the theorem is about something else.
          </p>
        </div>
      </section>

      <section className="card intro-goal">
        <span className="eyebrow">The goal</span>
        <h2>Review what matters, and measure how well it was reviewed.</h2>
        <p>
          The system takes a formalization apart automatically. Only the statement and the
          definitions it depends on need human judgement; for the example above that is one line,
          against more than fifty thousand declarations of the proof. Volunteers review them under a
          pseudonym, comparing each with the paper. Errors planted on purpose measure how reliable
          every reviewer is, so that the result is not a show of hands but a figure: how likely it
          is that an error went unnoticed. Every report is published, including negative ones.
        </p>
        <p>
          <a href="#/how">How a review works →</a>
        </p>
      </section>
    </>
  );
}
