// Hashtags of a problem (proposal C-44) and filter state kept in the session.
// The server normalizes tags itself (dpc/coord/tags.py); this mirrors it for
// the editor's preview and the click dummy.

const TAG = /^[a-z0-9][a-z0-9-]{0,38}[a-z0-9]$/;

/** `#Erdős Problems` → `erdos-problems`; null if no tag remains. */
export function normalizeTag(raw: string): string | null {
  const text = raw
    .trim()
    .replace(/^#+/, "")
    .trim()
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[\s_]+/g, "-");
  return TAG.test(text) && !text.includes("--") ? text : null;
}

/** Tags written with `#`, commas or spaces between them. */
export function parseTags(text: string): { tags: string[]; bad: string[] } {
  const tags: string[] = [];
  const bad: string[] = [];
  for (const part of text.split(/[,\s]+/)) {
    if (!part.replace(/#/g, "")) continue;
    const tag = normalizeTag(part);
    if (tag === null) bad.push(part);
    else if (!tags.includes(tag)) tags.push(tag);
  }
  return { tags, bad };
}

/** Does a search text match a title or one of the tags? `#x` searches tags only. */
export function matchesText(query: string, title: string, tags: string[] | undefined): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  if (q.startsWith("#")) return (tags ?? []).some((t) => t.includes(q.slice(1)));
  return title.toLowerCase().includes(q) || (tags ?? []).some((t) => t.includes(q));
}

/** Read a filter from the session, with defaults for what is missing. */
export function loadFilter<T extends object>(key: string, empty: T): T {
  try {
    return { ...empty, ...(JSON.parse(sessionStorage.getItem(key) ?? "{}") as Partial<T>) };
  } catch {
    return empty;
  }
}

/** Set parts of a stored filter before going to its page (a tag link). */
export function presetFilter<T extends object>(key: string, empty: T, patch: Partial<T>): void {
  sessionStorage.setItem(key, JSON.stringify({ ...empty, ...patch }));
}

/** Values with how often they occur, most frequent first; empty values dropped. */
export function tally(values: string[]): [string, number][] {
  const counts = new Map<string, number>();
  for (const v of values) if (v) counts.set(v, (counts.get(v) ?? 0) + 1);
  return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}
