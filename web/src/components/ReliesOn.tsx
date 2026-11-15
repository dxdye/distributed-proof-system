import { useState } from "react";
import type { GlossaryEntry } from "../api";
import { Origin } from "./Infoview";

// What a declaration takes from Mathlib and Lean (proposal C-27). The kernel
// checked the proof, not what the words of the statement mean: the statement
// means what these definitions mean, including the values they take where the
// paper's notion is undefined. Notation plumbing is left out (server side);
// it stays in the glossary of each component.

const FOLD = 8;

/** Docstrings are Markdown; show `code` spans as code, the rest as text. */
function docText(doc: string) {
  return doc.split("`").map((part, i) => (i % 2 === 1 ? <code key={i}>{part}</code> : part));
}

/** ``conventionsOnly``: inside an unfolded declaration, only the conventions to
 * know; the rest is on hover. */
export function ReliesOn({
  entries: given,
  conventionsOnly,
}: {
  entries?: GlossaryEntry[];
  conventionsOnly?: boolean;
}) {
  const [all, setAll] = useState(false);
  const entries = conventionsOnly ? given?.filter((g) => g.note) : given;
  if (!entries || entries.length === 0) return null;
  if (conventionsOnly)
    return (
      <section className="relies-on conventions-only" aria-label="Conventions to know">
        <h4>Conventions to know</h4>
        <ul>
          {entries.map((g) => (
            <li key={g.name}>
              <code>{g.name}</code>
              <p className="small glossary-note">{g.note}</p>
            </li>
          ))}
        </ul>
      </section>
    );
  const shown = all ? entries : entries.slice(0, FOLD);
  const noted = entries.filter((g) => g.note).length;
  return (
    <section className="relies-on" aria-label="Definitions it relies on">
      <h4>Definitions it relies on</h4>
      <p className="muted small">
        The kernel checked the proof, not what these words mean. The statement means what they mean:
        check that each one is the paper's notion, with the paper's conventions
        {noted > 0 &&
          (noted === 1 ? ". One has a convention to know" : `. ${noted} have conventions to know`)}
        .
      </p>
      <ul>
        {shown.map((g) => (
          <li key={g.name}>
            <div className="relies-head">
              <code>{g.name}</code> <Origin origin={g.origin} />
            </div>
            <code className="relies-type">{g.type}</code>
            {g.doc && <p className="small muted">{docText(g.doc)}</p>}
            {g.note && (
              <p className="small glossary-note">
                <strong>Convention:</strong> {g.note}
              </p>
            )}
          </li>
        ))}
      </ul>
      {entries.length > FOLD && (
        <button className="link small" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${entries.length}`}
        </button>
      )}
    </section>
  );
}
