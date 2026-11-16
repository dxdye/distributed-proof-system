import { useLayoutEffect, useRef, useState } from "react";
import type { Component, PaperPassage, UnitView } from "../api";
import { MathText } from "./MathText";
import { PaperPanel } from "./PaperPanel";

// What to compare the Lean statement with, behind one switch:
// - "Paper": the passage a maintainer mapped to the declaration (SR-24);
// - "LaTeX": the same Lean term typeset as a formula (where it can be typeset
//   unambiguously; the Lean text below stays the binding version).

type Tab = "paper" | "latex";

/** Typeset in text style so that long formulas wrap at relations and arrows.
 * `\left( … \right)` would make each bracketed part unbreakable, so plain
 * brackets are used for display; the stored LaTeX is unchanged. */
function breakable(latex: string): string {
  const plain = latex.replace(/\\left(?![a-zA-Z])/g, "").replace(/\\right(?![a-zA-Z])/g, "");
  return `$\\displaystyle ${allowBreaks(plain)}$`;
}

/** KaTeX breaks an inline formula only after relations and operators; long
 * chains such as `f(a, g(b, c), …)` have none and ran past the box. A break
 * is allowed after every comma outside a `{…}` group (so never inside
 * `\text{…}` and the like); escaped characters such as `\,` stay as they are. */
export function allowBreaks(tex: string): string {
  let depth = 0;
  let out = "";
  for (let i = 0; i < tex.length; i++) {
    const c = tex[i];
    if (c === "\\") {
      out += c + (tex[i + 1] ?? "");
      i++;
      continue;
    }
    if (c === "{") depth++;
    if (c === "}") depth--;
    out += c;
    if (c === "," && depth === 0) out += "\\allowbreak ";
  }
  return out;
}

function label(c: Component, kind: string): string {
  if (c.target === "type") return kind === "theorem" ? "Statement" : "Type";
  if (c.target === "value") return "Definition";
  return `Constructor ${c.label.split(".").pop() ?? c.label}`;
}

/** One formula; long ones start folded. */
function Formula({ component, kind }: { component: Component; kind: string }) {
  const box = useRef<HTMLDivElement>(null);
  const [long, setLong] = useState(false);
  const [open, setOpen] = useState(false);
  useLayoutEffect(() => {
    const el = box.current;
    if (el) setLong(el.scrollHeight > 170);
  }, [component.latex]);
  return (
    <div className="latex-item">
      <h4>{label(component, kind)}</h4>
      <div ref={box} className={long && !open ? "latex-body folded" : "latex-body"}>
        <MathText text={breakable(component.latex ?? "")} />
      </div>
      {long && (
        <button className="link small" onClick={() => setOpen(!open)}>
          {open ? "Show less" : "Show the whole formula"}
        </button>
      )}
    </div>
  );
}

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
          Paper: informal statement
        </button>
        <button role="tab" aria-pressed={tab === "latex"} onClick={() => setTab("latex")}>
          Lean: typeset as a formula
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
            <Formula key={`${c.target}:${c.label}`} component={c} kind={view.decl_kind} />
          ))}
          <details className="small muted latex-help">
            <summary>How to read the formula</summary>
            <p>
              It is the same Lean term, typeset; the Lean text below is the binding version. Types
              stay visible: division, subtraction and remainder on <MathText text="$\mathbb{N}$" />{" "}
              and <MathText text="$\mathbb{Z}$" /> carry a subscript (
              <MathText text="$a \mathbin{/_{\mathbb{N}}} b$" /> rounds down,{" "}
              <MathText text="$a \mathbin{-_{\mathbb{N}}} b$" /> stops at 0), a fraction is division
              in a field, and casts show their target type.
            </p>
          </details>
        </div>
      )}
    </section>
  );
}
