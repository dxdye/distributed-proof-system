// Layout of a Lean statement for reading (SR-21). Lean's pretty printer nests
// every `∧`, `∀` and `→` one level deeper, so a long statement becomes a
// staircase that drifts to the right. This lays the same text out again:
//
//   - a chain `A ∧ B ∧ C` (also `∨`, `↔`) puts its parts one below the other;
//   - `∀ x,`, `have x := v;` and hypotheses `h →` form a flat list, each `∀`
//     on one line with the hypotheses that follow it where they fit; the
//     conclusion comes last, indented once;
//   - `∃ x,` puts its body below, indented once;
//   - a relation (`≤`, `=`, `∈`, …) that does not fit breaks after the
//     operator, with the right side indented once;
//   - anything else is filled into lines, breaking inside brackets if needed.
//
// Only whitespace changes: the function checks that and otherwise returns the
// text unchanged. Originals and planted copies go through the same function, so
// the layout can make a copy stand out only where its text differs anyway.

const OPEN = "([{⟨⦃⟦⌊⌈";
const CLOSE = ")]}⟩⦄⟧⌋⌉";

/** Words that take everything to their right: an operator after them is theirs. */
const GREEDY = ["∀", "∃!", "∃", "fun", "λ", "have", "let", "if", "match", "show"];

/** Relations (precedence 50): weaker than arithmetic, stronger than `∧`. */
const RELATIONS = ["≤", "<", "=", "≠", "≥", ">", "∈", "∉", "⊆", "⊂", "∣", "≃", "≅"];

type Doc =
  | { t: "text"; s: string }
  | { t: "chain"; op: string; items: Doc[] }
  | { t: "rel"; op: string; lhs: Doc; rhs: Doc }
  | { t: "tele"; steps: string[]; body: Doc }
  | { t: "bind"; head: string; body: Doc }
  | { t: "paren"; inner: Doc };

const width = (s: string): number => [...s].length;
const squash = (s: string): string => s.replace(/\s+/g, " ").trim();
const spaces = (n: number): string => " ".repeat(n);

/** Bracket depth at each position; string literals count as one deeper. */
function depths(s: string): number[] {
  const out = new Array<number>(s.length);
  let depth = 0;
  let quoted = false;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (quoted) {
      out[i] = depth + 1;
      if (c === "\\" && i + 1 < s.length) out[++i] = depth + 1;
      else if (c === '"') quoted = false;
      continue;
    }
    if (c === '"') {
      out[i] = depth + 1;
      quoted = true;
      continue;
    }
    if (CLOSE.includes(c)) depth = Math.max(0, depth - 1);
    out[i] = depth;
    if (OPEN.includes(c)) depth++;
  }
  return out;
}

/** Does the word `w` start at position i, as a word of its own? */
function wordAt(s: string, i: number, w: string): boolean {
  if (!s.startsWith(w, i)) return false;
  const before = i === 0 ? " " : s[i - 1];
  const after = s[i + w.length] ?? " ";
  if (!/[\s(¬]/.test(before)) return false;
  return /[A-Za-z]/.test(w) ? /[\s({[⦃]/.test(after) : !/[A-Za-z0-9_']/.test(after);
}

/** First top-level greedy word (∀, ∃, fun, …); the text length if none. */
function firstGreedy(s: string, d: number[]): number {
  for (let i = 0; i < s.length; i++) {
    if (d[i] === 0 && GREEDY.some((w) => wordAt(s, i, w))) return i;
  }
  return s.length;
}

/** Top-level occurrences of ` op ` before `limit` (position of the space). */
function opsAt(s: string, d: number[], op: string, limit: number): number[] {
  const pat = ` ${op} `;
  const out: number[] = [];
  for (let i = s.indexOf(pat); i >= 0 && i < limit; i = s.indexOf(pat, i + 1)) {
    if (d[i] === 0 && d[i + 1] === 0) out.push(i);
  }
  return out;
}

/** The first top-level occurrence of `c`; -1 if none. */
function firstAt(s: string, d: number[], c: string): number {
  for (let i = 0; i < s.length; i++) if (d[i] === 0 && s[i] === c) return i;
  return -1;
}

/** A word that is one bracket pair around everything else. */
function bracketed(word: string): boolean {
  const open = OPEN.indexOf(word[0]);
  if (open < 0 || word.length < 2 || CLOSE.indexOf(word[word.length - 1]) !== open) return false;
  const d = depths(word);
  for (let k = 1; k < word.length - 1; k++) if (d[k] === 0) return false;
  return true;
}

function parse(s: string): Doc {
  s = s.trim();
  if (s[0] === "(" && bracketed(s)) {
    const inner = parse(s.slice(1, -1));
    return inner.t === "text" ? { t: "text", s } : { t: "paren", inner };
  }
  const d = depths(s);
  if (wordAt(s, 0, "∀")) {
    const end = firstAt(s, d, ",");
    if (end > 0) return tele(s.slice(0, end + 1), parse(s.slice(end + 1)));
  }
  if (wordAt(s, 0, "have") || wordAt(s, 0, "let")) {
    const end = firstAt(s, d, ";");
    if (end > 0) return tele(s.slice(0, end + 1), parse(s.slice(end + 1)));
  }
  if (wordAt(s, 0, "∃") || wordAt(s, 0, "∃!")) {
    const end = firstAt(s, d, ",");
    if (end > 0) return { t: "bind", head: s.slice(0, end + 1), body: parse(s.slice(end + 1)) };
  }
  // Operators by binding strength, weakest first; only up to the first word
  // that takes the rest of the text (operators after it are its own).
  const limit = firstGreedy(s, d);
  const iff = opsAt(s, d, "↔", limit);
  if (iff.length > 0) return chain(s, iff, "↔");
  const imp = opsAt(s, d, "→", limit);
  if (imp.length > 0) return tele(s.slice(0, imp[0]) + " →", parse(s.slice(imp[0] + 3)));
  for (const op of ["∨", "∧"]) {
    const at = opsAt(s, d, op, limit);
    if (at.length > 0) return chain(s, at, op);
  }
  if (!s.startsWith("¬")) {
    let first = -1;
    let op = "";
    for (const r of RELATIONS) {
      const at = opsAt(s, d, r, limit);
      if (at.length > 0 && (first < 0 || at[0] < first)) [first, op] = [at[0], r];
    }
    if (first > 0) {
      const rhs = s.slice(first + op.length + 2);
      return { t: "rel", op, lhs: parse(s.slice(0, first)), rhs: parse(rhs) };
    }
  }
  return { t: "text", s };
}

function chain(s: string, at: number[], op: string): Doc {
  const items: Doc[] = [];
  let from = 0;
  for (const i of at) {
    items.push(parse(s.slice(from, i)));
    from = i + op.length + 2;
  }
  items.push(parse(s.slice(from)));
  return { t: "chain", op, items };
}

function tele(step: string, body: Doc): Doc {
  return body.t === "tele"
    ? { t: "tele", steps: [step.trim(), ...body.steps], body: body.body }
    : { t: "tele", steps: [step.trim()], body };
}

function flat(doc: Doc): string {
  switch (doc.t) {
    case "text":
      return doc.s;
    case "chain":
      return doc.items.map(flat).join(` ${doc.op} `);
    case "rel":
      return `${flat(doc.lhs)} ${doc.op} ${flat(doc.rhs)}`;
    case "tele":
      return [...doc.steps, flat(doc.body)].join(" ");
    case "bind":
      return `${doc.head} ${flat(doc.body)}`;
    case "paren":
      return `(${flat(doc.inner)})`;
  }
}

/** Top-level words of a text, with brackets kept together. */
function words(s: string): string[] {
  const d = depths(s);
  const out: string[] = [];
  let from = 0;
  for (let i = 0; i < s.length; i++) {
    if (s[i] === " " && d[i] === 0) {
      if (i > from) out.push(s.slice(from, i));
      from = i + 1;
    }
  }
  if (from < s.length) out.push(s.slice(from));
  return out;
}

/** An infix operator: kept at the end of a line, never at the start. */
const OPERATOR = /^[^\sA-Za-z0-9_(){}[\]⟨⟩]{1,3}$/;
/** Prefix symbols look like operators but belong to what follows. */
const PREFIX = [
  "∑",
  "∏",
  "∫",
  "∫⁻",
  "∮",
  "⨆",
  "⨅",
  "⋃",
  "⋂",
  "¬",
  "↑",
  "⇑",
  "↥",
  "√",
  "-",
  "∀",
  "∃",
];
const infix = (word: string): boolean => OPERATOR.test(word) && !PREFIX.includes(word);

/** Fill a text into lines of at most `w` characters. A word too long on its
 * own is a bracket laid out inside (or left long: the block scrolls).
 * Continuation lines are indented once; an operator never starts a line. */
function fill(s: string, indent: number, w: number): string[] {
  if (indent + width(s) <= w || w - indent < NARROW) return [spaces(indent) + s];
  const out: string[] = [];
  let line = "";
  let at = indent;
  const all = words(s);
  for (let i = 0; i < all.length; i++) {
    const word = all[i];
    if (!line && out.length > 0 && infix(word) && width(out[out.length - 1]) < w) {
      out[out.length - 1] += ` ${word}`;
      continue;
    }
    const candidate = line ? `${line} ${word}` : word;
    if (at + width(candidate) <= w) {
      line = candidate;
      continue;
    }
    if (line) {
      out.push(spaces(at) + line);
      line = "";
      at = indent + 2;
    }
    if (at + width(word) <= w) {
      line = word;
    } else {
      // Room for an operator that will be attached after this word.
      const next = all[i + 1];
      const after = next !== undefined && infix(next) ? width(next) + 1 : 0;
      out.push(...inside(word, at, w - after));
      at = indent + 2;
    }
  }
  if (line) out.push(spaces(at) + line);
  return out;
}

/** A word as `pre ( body ) post`, e.g. `↑(f x)`, `(a, b).1`, `(x : T),`. */
function split(word: string): { pre: string; body: string; post: string } | null {
  const d = depths(word);
  let open = 0;
  while (open < word.length && !OPEN.includes(word[open])) open++;
  if (open >= word.length) return null;
  // Everything inside the bracket is deeper; the closing bracket is back at
  // the opening bracket's depth.
  let close = open + 1;
  while (close < word.length && d[close] !== d[open]) close++;
  if (close >= word.length || CLOSE.indexOf(word[close]) !== OPEN.indexOf(word[open])) return null;
  if ([...word.slice(close + 1)].some((c) => OPEN.includes(c))) return null;
  return {
    pre: word.slice(0, open + 1), // up to and with the opening bracket
    body: word.slice(open + 1, close),
    post: word.slice(close), // the closing bracket and what follows it
  };
}

/** A word too long for a line, laid out inside its bracket from column `at`;
 * left as it is (the block scrolls) if it has no bracket to break in. */
function inside(word: string, at: number, w: number): string[] {
  const parts = split(word);
  if (!parts) return [spaces(at) + word];
  const { pre, body, post } = parts;
  const lead = body.startsWith(" ") ? " " : "";
  const trail = body.endsWith(" ") ? " " : "";
  const col = at + width(pre) + lead.length;
  const lines = print(parse(body), col, w - width(post) - trail.length);
  lines[0] = spaces(at) + pre + lead + lines[0].slice(col);
  lines[lines.length - 1] += trail + post;
  return lines;
}

/** Telescope steps grouped for packing: each `∀` with the hypotheses after it;
 * a `have`/`let` on its own. */
function groups(steps: string[]): string[][] {
  const out: string[][] = [];
  let open = false; // may the next hypothesis join the last group?
  for (const step of steps) {
    if (step.startsWith("∀")) {
      out.push([step]);
      open = true;
    } else if (/^(have|let) /.test(step)) {
      out.push([step]);
      open = false;
    } else if (open) {
      out[out.length - 1].push(step);
    } else {
      out.push([step]);
      open = true;
    }
  }
  return out;
}

/** Below this many free characters, breaking further only makes a column of
 * single symbols; the rest is left to the browser's line wrapping. */
const NARROW = 24;

function print(doc: Doc, indent: number, w: number): string[] {
  const one = flat(doc);
  if (indent + width(one) <= w || w - indent < NARROW) return [spaces(indent) + one];
  switch (doc.t) {
    case "text":
      return fill(doc.s, indent, w);
    case "chain": {
      // Room for the operator that ends every part but the last.
      const out: string[] = [];
      doc.items.forEach((item, i) => {
        const last = i === doc.items.length - 1;
        const lines = print(item, indent, last ? w : w - width(doc.op) - 1);
        if (!last) lines[lines.length - 1] += ` ${doc.op}`;
        out.push(...lines);
      });
      return out;
    }
    case "rel": {
      const lines = print(doc.lhs, indent, w - width(doc.op) - 1);
      lines[lines.length - 1] += ` ${doc.op}`;
      return [...lines, ...print(doc.rhs, indent + 2, w)];
    }
    case "tele": {
      const out: string[] = [];
      for (const group of groups(doc.steps)) {
        let line = "";
        for (const step of group) {
          const candidate = line ? `${line} ${step}` : step;
          if (indent + width(candidate) <= w) {
            line = candidate;
            continue;
          }
          if (line) out.push(...fill(line, indent, w));
          line = step;
        }
        if (line) out.push(...fill(line, indent, w));
      }
      return [...out, ...print(doc.body, indent + 2, w)];
    }
    case "bind":
      return [...fill(doc.head, indent, w), ...print(doc.body, indent + 2, w)];
    case "paren": {
      const lines = print(doc.inner, indent + 1, w - 1);
      lines[0] = spaces(indent) + "(" + lines[0].slice(indent + 1);
      lines[lines.length - 1] += ")";
      return lines;
    }
  }
}

/** The statement laid out for lines of at most `w` characters. Returns the
 * text unchanged if the layout would change anything but whitespace. */
export function layoutTerm(text: string, w: number): string {
  const s = squash(text);
  if (!s) return text;
  let out: string;
  try {
    out = print(parse(s), 0, w)
      .map((l) => l.replace(/\s+$/, ""))
      .join("\n");
  } catch {
    return text;
  }
  return squash(out) === s ? out : text;
}
