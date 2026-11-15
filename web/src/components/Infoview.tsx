import { useMemo, useState } from "react";
import { kindLabel } from "../kinds";
import type { Component, GlossaryEntry, UnitView } from "../api";

// Static infoview (SR-21): the elaborated statement of each component, with the
// types of the constants it uses on hover and in a glossary. No local Lean needed.
//
// Every component is also rendered without the submission's own display rules
// (notation, coercions, unexpanders; ADR 0011). Where the two differ, the plain
// version comes first and the submission's version is shown below it.

const IDENT = /([A-Za-z_][A-Za-z0-9_.'!?₀-₉]*)/g;

function lookupTable(glossary: GlossaryEntry[]): Map<string, GlossaryEntry[]> {
  const table = new Map<string, GlossaryEntry[]>();
  for (const entry of glossary) {
    const parts = entry.name.split(".");
    for (let i = 0; i < parts.length; i++) {
      const key = parts.slice(i).join(".");
      table.set(key, [...(table.get(key) ?? []), entry]);
    }
  }
  return table;
}

/** A name with its type, origin, docstring and convention on hover and focus. */
function Const({ text, hits }: { text: string; hits?: GlossaryEntry[] }) {
  if (!hits) return <>{text}</>;
  return (
    <span className="const" tabIndex={0}>
      {text}
      <span className="hover" role="tooltip">
        {hits.map((h) => (
          <span key={h.name} className="hover-line">
            <b>{h.name}</b> : {h.type} <Origin origin={h.origin} />
            {h.doc && <span className="hover-doc">{h.doc}</span>}
            {h.note && <span className="hover-note">{h.note}</span>}
          </span>
        ))}
      </span>
    </span>
  );
}

export function Term({ text, glossary }: { text: string; glossary: GlossaryEntry[] }) {
  const table = useMemo(() => lookupTable(glossary), [glossary]);
  const pieces = text.split(IDENT);
  return (
    <pre className="term">
      {pieces.map((piece, i) => {
        if (i % 2 === 0) return <span key={i}>{piece}</span>;
        const whole = table.get(piece);
        if (whole || !piece.includes(".")) return <Const key={i} text={piece} hits={whole} />;
        // Generalized field notation, possibly chained: `n.primeFactors.card`,
        // `(a + i).natAbs.Coprime n`. Look up every link on its own.
        const links = piece.split(".");
        return (
          <span key={i}>
            {links.map((link, j) => (
              <span key={j}>
                {j > 0 && "."}
                <Const text={link} hits={table.get(link)} />
              </span>
            ))}
          </span>
        );
      })}
    </pre>
  );
}

const ORIGIN_LABELS: Record<string, string> = {
  core: "Lean",
  library: "Mathlib",
  submission: "this submission",
};

/** Where a constant comes from: Lean, a hardened library, or the submission
 * itself (whose definitions are under review too). */
export function Origin({ origin }: { origin?: string | null }) {
  if (!origin) return null;
  return <span className={`badge origin origin-${origin}`}>{ORIGIN_LABELS[origin] ?? origin}</span>;
}

function heading(c: Component, kind: string): string {
  if (c.target === "type") return kind === "theorem" ? "Statement" : "Type";
  if (c.target === "value") return "Definition";
  return `Constructor ${c.label}`;
}

export function displayDiffers(c: Component): boolean {
  return c.trusted_text != null && c.trusted_text !== c.text;
}

function ComponentBox({ component, kind }: { component: Component; kind: string }) {
  const [open, setOpen] = useState(false);
  const differs = displayDiffers(component);
  // Hover types and glossary always from the plain rendering when there is one:
  // the submission's notation could make a constant's type look different too.
  const glossary =
    component.trusted_text != null ? (component.trusted_glossary ?? []) : component.glossary;
  return (
    <section className={differs ? "component differs" : "component"}>
      <h4>{heading(component, kind)}</h4>
      {differs ? (
        <>
          <p className="term-label">Plain: Lean and Mathlib notation only</p>
          <Term text={component.trusted_text ?? ""} glossary={glossary} />
          <p className="term-label">As the submission displays it</p>
          <Term text={component.text} glossary={component.glossary} />
        </>
      ) : (
        <Term text={component.text} glossary={glossary} />
      )}
      {glossary.length > 0 && (
        <div className="glossary">
          <button className="link" onClick={() => setOpen(!open)}>
            {open ? "Hide" : "Show"}{" "}
            {glossary.length === 1 ? "the constant" : `the ${glossary.length} constants`} used
          </button>
          {open && (
            <table>
              <tbody>
                {glossary.map((g) => (
                  <tr key={g.name}>
                    <td>
                      <span className="mono">{g.name}</span> <Origin origin={g.origin} />
                    </td>
                    <td>
                      <span className="mono small">{g.type}</span>
                      {g.doc && <p className="small muted glossary-doc">{g.doc}</p>}
                      {g.note && <p className="small glossary-note">{g.note}</p>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </section>
  );
}

/** ``hideContext``: where the neighbours are shown unfoldable instead (TicketContext). */
export function Infoview({ view, hideContext }: { view: UnitView; hideContext?: boolean }) {
  const differing = view.components.filter(displayDiffers).length;
  return (
    <div className="infoview">
      <div className="decl-head">
        <span className="badge">{kindLabel(view.decl_kind)}</span>
        <code>{view.declaration}</code>
      </div>
      {differing > 0 && (
        <p className="display-warning">
          The submission's own display rules change how{" "}
          {differing === 1
            ? "one part of this declaration looks"
            : `${differing} parts of this declaration look`}
          . Both versions are shown below. The plain one is what the declaration actually says;
          judge that one.
        </p>
      )}
      {view.components.map((c) => (
        <ComponentBox key={`${c.target}:${c.label}`} component={c} kind={view.decl_kind} />
      ))}
      {!hideContext && view.context.length > 0 && (
        <p className="muted small">
          Builds on (also under review):{" "}
          {view.context.map((c) => (
            <code key={c}>{c} </code>
          ))}
        </p>
      )}
    </div>
  );
}
