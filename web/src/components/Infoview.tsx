import { useMemo, useState } from "react";
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

function Term({ text, glossary }: { text: string; glossary: GlossaryEntry[] }) {
  const table = useMemo(() => lookupTable(glossary), [glossary]);
  const pieces = text.split(IDENT);
  return (
    <pre className="term">
      {pieces.map((piece, i) => {
        const hits = i % 2 === 1 ? table.get(piece) : undefined;
        if (!hits) return <span key={i}>{piece}</span>;
        return (
          <span key={i} className="const" tabIndex={0}>
            {piece}
            <span className="hover" role="tooltip">
              {hits.map((h) => (
                <span key={h.name} className="hover-line">
                  <b>{h.name}</b> : {h.type}
                </span>
              ))}
            </span>
          </span>
        );
      })}
    </pre>
  );
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
            {open ? "Hide" : "Show"} the {glossary.length} constants used
          </button>
          {open && (
            <table>
              <tbody>
                {glossary.map((g) => (
                  <tr key={g.name}>
                    <td className="mono">{g.name}</td>
                    <td className="mono small">{g.type}</td>
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

export function Infoview({ view }: { view: UnitView }) {
  const differing = view.components.filter(displayDiffers).length;
  return (
    <div className="infoview">
      <div className="decl-head">
        <span className="badge">{view.decl_kind}</span>
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
      {view.context.length > 0 && (
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
