import { useMemo, useState } from "react";
import type { Component, GlossaryEntry, UnitView } from "../api";

// Static infoview (SR-21): the elaborated statement of each component, with the
// types of the constants it uses on hover and in a glossary. No local Lean needed.

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

function ComponentBox({ component, kind }: { component: Component; kind: string }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="component">
      <h4>{heading(component, kind)}</h4>
      <Term text={component.text} glossary={component.glossary} />
      {component.glossary.length > 0 && (
        <div className="glossary">
          <button className="link" onClick={() => setOpen(!open)}>
            {open ? "Hide" : "Show"} the {component.glossary.length} constants used
          </button>
          {open && (
            <table>
              <tbody>
                {component.glossary.map((g) => (
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
  return (
    <div className="infoview">
      <div className="decl-head">
        <span className="badge">{view.decl_kind}</span>
        <code>{view.declaration}</code>
      </div>
      {view.components.map((c) => (
        <ComponentBox key={`${c.target}:${c.label}`} component={c} kind={view.decl_kind} />
      ))}
      {view.context.length > 0 && (
        <p className="muted small">
          Builds on (also under review): {view.context.map((c) => <code key={c}>{c} </code>)}
        </p>
      )}
    </div>
  );
}
