import { useEffect, useRef, useState } from "react";
import { MathText } from "../components/MathText";

// Subpages of "How it works": the organisation, planted errors, and why the
// statistics hold. The mechanism is public (the code is open source, and
// security must not rest on keeping it secret, Kerckhoffs). Secret is only
// which ticket is planted, until the reveal, and the salts of the commitments.
// Numbers are the defaults (dpc/coord/params.py, dpc/domain/decision.py); the
// running service records the parameters it uses in its public log.

export const HOW_PAGES: { slug: string; title: string; summary: string }[] = [
  {
    slug: "organisation",
    title: "Organisation and roles",
    summary: "Who does what, how roles are earned or appointed, and why they are kept apart.",
  },
  {
    slug: "planted-errors",
    title: "Planted errors",
    summary: "What they are, how they are made and mixed in, and why they stay secret until later.",
  },
  {
    slug: "statistics",
    title: "Why the statistics hold",
    summary: "How reliability is measured, how verdicts are combined, and what the figure means.",
  },
];

/** The tab bar of the How pages. It sticks below the header once it would
 * scroll away (desktop), with a shadow while it floats over the content. */
export function HowNav({ current }: { current?: string }) {
  const sentinel = useRef<HTMLDivElement>(null);
  const [stuck, setStuck] = useState(false);
  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const top =
      parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--masthead-h")) || 0;
    const observer = new IntersectionObserver(([entry]) => setStuck(!entry.isIntersecting), {
      rootMargin: `-${Math.round(top) + 1}px 0px 0px 0px`,
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return (
    <>
      <div ref={sentinel} className="how-nav-sentinel" aria-hidden="true" />
      <nav className={stuck ? "how-nav stuck" : "how-nav"} aria-label="How it works">
        <span className="how-nav-label" aria-hidden="true">
          Sections
        </span>
        <a href="#/how" aria-current={current ? undefined : "page"}>
          Overview
        </a>
        {HOW_PAGES.map((p) => (
          <a
            key={p.slug}
            href={`#/how/${p.slug}`}
            aria-current={current === p.slug ? "page" : undefined}
          >
            {p.title}
          </a>
        ))}
      </nav>
    </>
  );
}

function Open() {
  return (
    <section className="card how-open">
      <h2>Nothing here is secret but the key</h2>
      <p>
        Security must not depend on keeping the mechanism secret (Kerckhoffs' principle). The code
        of this service will be open source, and these pages describe the mechanism completely. What
        stays secret is small and temporary: <b>which</b> ticket carries a planted error, until it
        is revealed, and the random salts that seal this in advance. Everything else can be checked
        by anyone, and the audit log is published with every report.
      </p>
    </section>
  );
}

export function HowOrganisation() {
  return (
    <div className="how">
      <HowNav current="organisation" />
      <section className="hero">
        <span className="eyebrow">How it works</span>
        <h1>Organisation and roles</h1>
        <p className="lead">
          Two ladders: weight is earned by measurement, per domain; tasks are appointed. They meet
          in one place only: a maintainer must have earned the re-checker role in the domain first.
        </p>
      </section>
      <section className="card">
        <pre className="how-ladder">{`  Administrator        platform · appointed · few
        │ appoints
  Maintainer           per domain · appointed · requires PVV there
        │ requires
  ┌─ earned, measured per domain ───────────────┐
  Re-checker (PVV)     high measured reliability
  Reviewer (PV)        measured reliability
  Newcomer             everyone after sign-up`}</pre>
      </section>
      <section className="card">
        <h2>Who may do what</h2>
        <table className="how-table">
          <thead>
            <tr>
              <th />
              <th>Newcomer</th>
              <th>PV</th>
              <th>PVV</th>
              <th>Maintainer</th>
              <th>Administrator</th>
            </tr>
          </thead>
          <tbody>
            {(
              [
                ["Review tickets, discuss", "✓", "✓", "✓", "✓¹", "—"],
                ["Vote with weight", "little", "✓", "✓", "✓¹", "—"],
                ["Re-checks, decide claimed errors", "", "", "✓", "✓¹", "—"],
                ["Propose passages, hashtags, domains", "", "", "✓", "✓", ""],
                ["Confirm them (second pair of eyes)", "", "", "", "✓", ""],
                ["Decide escalations (panel of three)", "", "", "", "✓", ""],
                ["Moderation, reopen requests", "", "", "", "✓", ""],
                ["Open and close submissions", "", "", "", "", "✓"],
                ["Appoint maintainers (public, with reason)", "", "", "", "", "✓"],
              ] as string[][]
            ).map((row) => (
              <tr key={row[0]}>
                {row.map((cell, i) =>
                  i === 0 ? <th key={i}>{cell}</th> : <td key={i}>{cell}</td>,
                )}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="small muted">
          ¹ Only with the reliability they earned in that domain, never by appointment; and not on a
          declaration whose original they saw as maintainer.
        </p>
      </section>
      <section className="card">
        <h2>The rules behind it</h2>
        <ol>
          <li>
            <b>Whoever knows the internals of review does not review.</b> Administrators can see
            which tickets are planted; they take no tickets. A maintainer who looked at the original
            of a declaration under review is not offered its tickets afterwards.
          </li>
          <li>
            <b>Weight comes only from measurement.</b> An appointment gives tasks, not weight. The
            exception is the start of a new domain, when nobody can have earned anything yet:
            founding maintainers count as re-checkers there until a public end date.
          </li>
          <li>
            <b>Content needs four eyes.</b> One person proposes a paper passage or a correction, a
            maintainer of the domain confirms it.
          </li>
          <li>
            <b>No single person decides a disputed declaration.</b> Escalations go to a panel of
            three maintainers of the domain, who vote without seeing each other's votes.
          </li>
          <li>
            <b>Every appointment is public</b>, in the audit log, with its reason and its end date.
          </li>
        </ol>
        <p className="small muted">
          Rule 4 is being introduced: until then one maintainer of the domain decides an escalation.
        </p>
        <p className="small muted">
          Test systems also have <i>root testers</i>, who hold every role at once to try every page.
          They exist only where the service is configured for it, never in production.
        </p>
      </section>
      <Open />
    </div>
  );
}

export function HowPlantedErrors() {
  return (
    <div className="how">
      <HowNav current="planted-errors" />
      <section className="hero">
        <span className="eyebrow">How it works</span>
        <h1>Planted errors</h1>
        <p className="lead">
          A few tickets carry an error put there on purpose. They are how the service measures how
          reliable each review is: agreement alone cannot tell a careful reviewer from someone who
          clicks "correct" every time, because almost every statement is correct.
        </p>
      </section>
      <section className="card">
        <h2>How they are made</h2>
        <p>
          A planted error starts from a real declaration of the submission. The service changes its
          statement slightly, the way formalization errors really happen, and has Lean check that
          the changed statement is still well-formed. Changes that turn out to mean the same thing
          as the original are dropped. The copy keeps everything else of the original: the same
          paper passage, the same context, the same questions.
        </p>
        <p>
          The guiding rule: <b>a planted copy may stand out only in ways a real error can.</b> So
          during the review nothing proven about the declaration is shown, and every aid a ticket
          offers is produced for the copy in the same way as for the original.
        </p>
      </section>
      <section className="card">
        <h2>How they are mixed in, and sealed</h2>
        <ul>
          <li>
            About one ticket in ten is planted (the default share). Planted tickets enter the same
            stream as real ones and are drawn the same way.
          </li>
          <li>
            When a ticket is created, the service publishes a <i>commitment</i>: a hash of "real or
            planted" together with a random salt. The answer itself stays in a separate vault. When
            it is revealed, anyone can check that it matches the commitment made beforehand: the
            service cannot decide afterwards which tickets were planted.
          </li>
          <li>
            Each person sees each declaration in one version only. Someone who had the copy never
            gets the original, and the other way round: comparing the two would find the copy
            without any mathematics.
          </li>
        </ul>
      </section>
      <section className="card">
        <h2>When you learn about them</h2>
        <p>
          Planted errors are revealed later and in batches: by default no earlier than a week after
          their decision, and only once at least five are due, all of them together. Revealed one by
          one and at once, the timing would tell which of the open tickets are planted. Discussion
          of a declaration opens only after every planted error of its submission is revealed.
        </p>
        <p>
          Finding a planted error counts as much as finding a real one; missing one lowers your
          measured sensitivity. Whoever missed one gets the explanation privately.
        </p>
      </section>
      <section className="card">
        <h2>What is not advertised, and why</h2>
        <p>
          The kinds of changes are in the open-source code; they are not listed here. A list on this
          page would invite looking for the list instead of for errors: reviewers would learn the
          patterns of the planted errors, be measured as reliable, and still miss real errors of
          other kinds. This is not secrecy of the mechanism: nothing depends on it except the
          quality of the measurement, and the code shows it to anyone who looks.
        </p>
      </section>
      <Open />
    </div>
  );
}

export function HowStatistics() {
  return (
    <div className="how">
      <HowNav current="statistics" />
      <section className="hero">
        <span className="eyebrow">How it works</span>
        <h1>Why the statistics hold</h1>
        <p className="lead">
          The result of a review is not a show of hands but a probability: how likely it is that a
          declaration accepted by the reviewers is wrong after all. Three things make that
          probability meaningful.
        </p>
      </section>
      <section className="card">
        <h2>1 · Reliability is measured, with two numbers</h2>
        <p>
          <MathText text="For every person and domain the service estimates the sensitivity $s$, the chance of reporting an error that is there, and the specificity $c$, the chance of confirming a correct statement as correct." />
        </p>
        <p>
          Both are needed. Errors are rare, so someone who always answers "correct" is right almost
          always, and has <MathText text="$s \approx 0$" />. Planted errors measure{" "}
          <MathText text="$s$" />: they look like real tickets, so the share found estimates the
          share of real errors found. Each rate is a Beta distribution; what counts is its lower
          bound, <MathText text="$\kappa = \min(\mathrm{LB}(s), \mathrm{LB}(c))$" />, so that a few
          lucky answers do not make anyone reliable.
        </p>
        <p>
          Evidence has different weight: planted errors and errors refuted by a machine count fully,
          re-checks by a PVV about half, plain agreement with others about a fifth.{" "}
          <b>Trust cannot be built by confirming each other.</b>
        </p>
      </section>
      <section className="card">
        <h2>2 · Verdicts are combined as evidence</h2>
        <p>
          <MathText text="Each verdict $y_j$ ($1$ for 'incorrect') multiplies the odds that the declaration is wrong, starting from a prior $\pi_0$:" />
        </p>
        <p className="math-display">
          <MathText text="$$\log\frac{P(\text{wrong})}{P(\text{right})} = \log\frac{\pi_0}{1-\pi_0} + \sum_j \Big[\, y_j \log\frac{s_j}{1-c_j} + (1-y_j)\log\frac{1-s_j}{c_j} \Big]$$" />
        </p>
        <p>
          A careful reviewer moves the odds a lot, a careless one hardly at all. Example, with the
          default prior of 2 %: three reviewers with <MathText text="$s = 0.8$, $c = 0.95$" /> all
          say "correct". Each multiplies the odds by <MathText text="$0.2/0.95 \approx 0.21$" />,
          and the probability of an error falls to about <b>0.02 %</b>. Three people who click
          "correct" every time (<MathText text="$s = 0.1$, $c = 0.99$" />) multiply by{" "}
          <MathText text="$0.91$" /> each and leave it at about <b>1.5 %</b>: not enough, so the
          declaration gets more reviews.
        </p>
        <p>The rule, with the default values:</p>
        <ul>
          <li>
            <b>Accepted</b> when the probability of an error is below 0.1 %, at least three
            independent verdicts are in, and a re-checker has looked at it.
          </li>
          <li>
            <b>Error</b> when it is above 99.9 %, or a claimed error is confirmed. A single
            justified "incorrect" is never outvoted: it becomes a claim that a re-checker decides.
          </li>
          <li>
            Otherwise more reviews; after three rounds without a decision, an escalation to the
            maintainers of the domain.
          </li>
        </ul>
      </section>
      <section className="card">
        <h2>3 · The verdicts are independent</h2>
        <p>
          Multiplying the evidence is right only if the verdicts are independent. That is what most
          rules of the service are for: nobody sees other verdicts before the decision; discussion
          opens only afterwards; each person sees a declaration in one version; tickets are drawn,
          not chosen freely, and rerolling is limited, so that no group can gather on one ticket;
          authors and their labs do not review their own work.
        </p>
      </section>
      <section className="card">
        <h2>What the figure on the progress page means</h2>
        <p>
          <MathText text="For a paper, the residual error is the probability that at least one of its accepted declarations is wrong: $1 - \prod_i (1 - p_i)$ over the accepted declarations $i$." />{" "}
          It is an estimate, as good as the measurement of reliability behind it; that is why the
          planted errors keep running for as long as the service does.
        </p>
      </section>
      <Open />
    </div>
  );
}
