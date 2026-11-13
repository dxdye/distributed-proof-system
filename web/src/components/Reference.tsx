import { useState } from "react";
import type { PaperPassage, UnitView } from "../api";
import { MathText } from "./MathText";
import { PaperPanel } from "./PaperPanel";

// What to compare the Lean statement with, behind one switch:
// - "Paper": the passage a maintainer mapped to the declaration (SR-24);
// - "LaTeX": the same Lean term typeset as a formula (where it can be typeset
//   unambiguously; the Lean text below stays the binding version).

type Tab = "paper" | "latex";

export function Reference({
  view,
  passage,
  paperRef,
  leaseId,
  contested,
  minChars,
  active,
}: {
  view: UnitView;
  passage: PaperPassage | null;
  paperRef: string | null;
  leaseId: string;
  contested: boolean;
  minChars: number;
  active: boolean;
}) {
  const [tab, setTab] = useState<Tab>("paper");
  const typeset = view.components.filter((c) => c.latex);
  return (
    <section className="reference">
      <div className="segmented" role="tablist" aria-label="Reference">
        <button role="tab" aria-pressed={tab === "paper"} onClick={() => setTab("paper")}>
          The paper says
        </button>
        <button role="tab" aria-pressed={tab === "latex"} onClick={() => setTab("latex")}>
          As a formula (LaTeX)
        </button>
      </div>
      {tab === "paper" ? (
        <PaperPanel
          passage={passage}
          paperRef={paperRef}
          leaseId={leaseId}
          contested={contested}
          minChars={minChars}
          active={active}
        />
      ) : typeset.length === 0 ? (
        <p className="muted reference-empty">
          No typeset version of this declaration is available yet. The Lean statement below is the
          binding one.
        </p>
      ) : (
        <div className="latex-panel">
          {typeset.map((c) => (
            <div key={`${c.target}:${c.label}`} className="latex-item">
              <MathText text={`$$${c.latex}$$`} />
            </div>
          ))}
          <p className="small muted">
            The same Lean term, typeset. Types and coercions are kept; the Lean text below is the
            binding version.
          </p>
        </div>
      )}
    </section>
  );
}
