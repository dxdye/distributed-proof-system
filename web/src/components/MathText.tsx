import katex from "katex";
import "katex/dist/katex.min.css";
import { Fragment, useMemo } from "react";

// Text with LaTeX math between $…$ (inline) or $$…$$ (display), typeset with
// KaTeX (MIT, bundled: no third-party requests). Plain text stays plain React
// text; only KaTeX's own output is inserted as HTML. `trust: false` keeps
// commands such as \href and \url out.

type Piece = { math: boolean; display: boolean; text: string };

function split(source: string): Piece[] {
  const pieces: Piece[] = [];
  const re = /\$\$([\s\S]+?)\$\$|\$([^$]+?)\$/g;
  let last = 0;
  for (const m of source.matchAll(re)) {
    const at = m.index ?? 0;
    if (at > last) pieces.push({ math: false, display: false, text: source.slice(last, at) });
    pieces.push({ math: true, display: m[1] !== undefined, text: m[1] ?? m[2] ?? "" });
    last = at + m[0].length;
  }
  if (last < source.length) pieces.push({ math: false, display: false, text: source.slice(last) });
  return pieces;
}

export function MathText({ text }: { text: string }) {
  const pieces = useMemo(() => split(text), [text]);
  return (
    <span className="math-text">
      {pieces.map((p, i) =>
        p.math ? (
          <span
            key={i}
            className={p.display ? "math-display" : undefined}
            // KaTeX output only; errors are shown as the source in red.
            dangerouslySetInnerHTML={{
              __html: katex.renderToString(p.text, {
                displayMode: p.display,
                throwOnError: false,
                trust: false,
                strict: "ignore",
                output: "htmlAndMathml",
              }),
            }}
          />
        ) : (
          <Fragment key={i}>{p.text}</Fragment>
        ),
      )}
    </span>
  );
}
