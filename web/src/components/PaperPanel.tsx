import { useState } from "react";
import { api, type PaperPassage } from "../api";
import { MathText } from "./MathText";

// "The paper says": the passage a maintainer mapped to this declaration
// (SR-24). Reviewers compare the Lean statement with it, and can contest the
// mapping when the passage does not belong here.

export function PaperPanel({
  passage,
  paperRef,
  leaseId,
  contested,
  minChars,
  active,
}: {
  passage: PaperPassage | null;
  paperRef: string | null;
  leaseId: string;
  contested: boolean;
  minChars: number;
  active: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [sent, setSent] = useState(contested);
  const [error, setError] = useState<string | null>(null);

  if (!passage) {
    return (
      <section className="paper-panel missing">
        <h3>The paper says</h3>
        <p>
          No passage of the paper has been mapped to this declaration yet. Look it up yourself
          {paperRef ? (
            <>
              {" "}
              (
              {/^https?:\/\//.test(paperRef) ? (
                <a href={paperRef} rel="noreferrer">
                  the paper
                </a>
              ) : (
                <span className="mono">{paperRef}</span>
              )}
              )
            </>
          ) : null}
          , and say in your justification which passage you compared with.
        </p>
      </section>
    );
  }

  const src = passage.source;
  const id = src.arxiv ? `arXiv:${src.arxiv}${src.version ?? ""}` : null;
  async function contest() {
    setError(null);
    try {
      await api.contestMapping(leaseId, reason);
      setSent(true);
      setOpen(false);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <section className="paper-panel">
      <h3>The paper says</h3>
      <p className="paper-source small">
        {src.url ? <a href={src.url}>{src.title}</a> : src.title}
        {id && <span className="mono"> · {id}</span>} · <strong>{passage.locator}</strong>
      </p>
      <blockquote className="paper-statement">
        <MathText text={passage.statement} />
      </blockquote>
      {passage.note && <p className="small muted">{passage.note}</p>}
      <p className="small muted">
        Mapped by {passage.mapped_by}.{" "}
        {sent ? (
          <span>You reported that this passage does not match. Maintainers will look at it.</span>
        ) : (
          active && (
            <button className="link" onClick={() => setOpen(!open)}>
              This passage does not belong to this declaration
            </button>
          )
        )}
      </p>
      {open && !sent && (
        <div className="contest">
          <label>
            What is wrong with the mapping? (at least {minChars} characters)
            <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          {error && <p className="error">{error}</p>}
          <button
            className="secondary"
            disabled={reason.trim().length < minChars}
            onClick={contest}
          >
            Report the mapping
          </button>
        </div>
      )}
    </section>
  );
}
