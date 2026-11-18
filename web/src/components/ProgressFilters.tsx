import { useEffect, useMemo, useState } from "react";
import type { ProgressSummary } from "../api";
import { domainLabel } from "../kinds";
import { loadFilter, matchesText, presetFilter, tally } from "../tags";

// Filters of the progress page: search (titles and hashtags), hashtag,
// domain, source, status, order. The state lives in the session, so it
// survives the way to a paper and back.

type Status = "all" | "not-started" | "in-review" | "complete" | "findings" | "closed";
type Order = "newest" | "progress" | "interest" | "title";

export type Filter = {
  q: string;
  tag: string;
  domain: string;
  source: string;
  status: Status;
  order: Order;
};

const EMPTY: Filter = { q: "", tag: "", domain: "", source: "", status: "all", order: "newest" };
const KEY = "dpc.progress-filter";

/** A link to the list of papers with one hashtag (C-44). */
export const progressTagLink = (tag: string) => ({
  href: "#/progress",
  onClick: () => presetFilter(KEY, EMPTY, { tag }),
});

const STATUSES: {
  key: Exclude<Status, "all">;
  label: string;
  test: (s: ProgressSummary) => boolean;
}[] = [
  {
    key: "not-started",
    label: "Not started",
    test: (s) => !s.closed && s.decided === 0 && s.in_review === 0,
  },
  {
    key: "in-review",
    label: "In review",
    test: (s) => !s.closed && s.decided < s.declarations && (s.in_review > 0 || s.decided > 0),
  },
  {
    key: "complete",
    label: "Complete",
    test: (s) => s.declarations > 0 && s.decided === s.declarations,
  },
  { key: "findings", label: "With findings", test: (s) => s.errors > 0 },
  { key: "closed", label: "Closed", test: (s) => s.closed },
];

const ORDERS: { key: Order; label: string }[] = [
  { key: "newest", label: "Newest first" },
  { key: "progress", label: "Most decided" },
  { key: "interest", label: "Most interest" },
  { key: "title", label: "Title" },
];

/** Where a submission comes from: owner/repository on GitHub, else host/path. */
export function sourceOf(repoUrl: string): string {
  try {
    const url = new URL(repoUrl);
    const path = url.pathname.split("/").filter(Boolean);
    return url.host === "github.com" ? path.slice(0, 2).join("/") : [url.host, ...path].join("/");
  } catch {
    return repoUrl;
  }
}

function matches(s: ProgressSummary, f: Filter, withStatus: boolean): boolean {
  if (!matchesText(f.q, s.title, s.tags)) return false;
  if (f.tag && !(s.tags ?? []).includes(f.tag)) return false;
  if (f.domain && s.domain !== f.domain) return false;
  if (f.source && sourceOf(s.repo_url) !== f.source) return false;
  if (withStatus && f.status !== "all") {
    const status = STATUSES.find((x) => x.key === f.status);
    if (status && !status.test(s)) return false;
  }
  return true;
}

function ordered(list: ProgressSummary[], order: Order): ProgressSummary[] {
  const out = [...list];
  if (order === "progress") out.sort((a, b) => b.coverage - a.coverage);
  if (order === "interest") out.sort((a, b) => (b.interest ?? -1) - (a.interest ?? -1));
  if (order === "title") out.sort((a, b) => a.title.localeCompare(b.title));
  return out; // "newest": as the server sends them
}

/** The papers to show, and the filter row that chooses them. */
export function useProgressFilter(list: ProgressSummary[]) {
  const [filter, setFilter] = useState<Filter>(() => loadFilter(KEY, EMPTY));
  useEffect(() => sessionStorage.setItem(KEY, JSON.stringify(filter)), [filter]);
  const shown = useMemo(
    () =>
      ordered(
        list.filter((s) => matches(s, filter, true)),
        filter.order,
      ),
    [list, filter],
  );
  return { filter, setFilter, shown };
}

export function ProgressFilters({
  list,
  filter,
  setFilter,
  shown,
}: {
  list: ProgressSummary[];
  filter: Filter;
  setFilter: (f: Filter) => void;
  shown: number;
}) {
  const set = (patch: Partial<Filter>) => setFilter({ ...filter, ...patch });
  const tags = useMemo(() => tally(list.flatMap((s) => s.tags ?? [])), [list]);
  const domains = useMemo(() => tally(list.map((s) => s.domain ?? "")), [list]);
  const sources = useMemo(() => tally(list.map((s) => sourceOf(s.repo_url))), [list]);
  // Counts per status under the other filters, so a click never leads to nothing unexpected.
  const rest = list.filter((s) => matches(s, filter, false));
  const active =
    filter.q !== "" ||
    filter.tag !== "" ||
    filter.domain !== "" ||
    filter.source !== "" ||
    filter.status !== "all";
  return (
    <section className="progress-filters" aria-label="Filter the papers">
      <div className="filter-row">
        <input
          type="search"
          placeholder="Search titles and #hashtags"
          aria-label="Search titles and hashtags"
          value={filter.q}
          onChange={(e) => set({ q: e.target.value })}
        />
        {tags.length > 0 && (
          <select
            aria-label="Hashtag"
            value={filter.tag}
            onChange={(e) => set({ tag: e.target.value })}
          >
            <option value="">All hashtags</option>
            {tags.map(([t, n]) => (
              <option key={t} value={t}>
                #{t} ({n})
              </option>
            ))}
          </select>
        )}
        <select
          aria-label="Domain"
          value={filter.domain}
          onChange={(e) => set({ domain: e.target.value })}
        >
          <option value="">All domains</option>
          {domains.map(([d, n]) => (
            <option key={d} value={d}>
              {domainLabel(d)} ({n})
            </option>
          ))}
        </select>
        {sources.length > 1 && (
          <select
            aria-label="Source"
            value={filter.source}
            onChange={(e) => set({ source: e.target.value })}
          >
            <option value="">All sources</option>
            {sources.map(([src, n]) => (
              <option key={src} value={src}>
                {src} ({n})
              </option>
            ))}
          </select>
        )}
        <select
          className="filter-order"
          aria-label="Order"
          value={filter.order}
          onChange={(e) => set({ order: e.target.value as Order })}
        >
          {ORDERS.map((o) => (
            <option key={o.key} value={o.key}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <div className="filter-row">
        <div className="segmented" role="group" aria-label="Status">
          <button aria-pressed={filter.status === "all"} onClick={() => set({ status: "all" })}>
            All {rest.length}
          </button>
          {STATUSES.map((st) => {
            const n = rest.filter(st.test).length;
            return (
              <button
                key={st.key}
                aria-pressed={filter.status === st.key}
                onClick={() => set({ status: st.key })}
                disabled={n === 0 && filter.status !== st.key}
              >
                {st.label} {n}
              </button>
            );
          })}
        </div>
        <p className="muted small filter-count" aria-live="polite">
          {shown === list.length ? `${list.length} papers` : `${shown} of ${list.length} papers`}
          {active && (
            <>
              {" · "}
              <button className="link" onClick={() => setFilter({ ...EMPTY, order: filter.order })}>
                Clear filters
              </button>
            </>
          )}
        </p>
      </div>
    </section>
  );
}
