import { useEffect, useMemo, useState } from "react";
import type { ThreadSummary } from "../api";
import { domainLabel } from "../kinds";
import { loadFilter, matchesText, presetFilter, tally } from "../tags";

// Filters of the discussions: search (declaration, paper, hashtags),
// hashtag, paper, domain, outcome, "reviews I can share", order. Kept in the
// session like the progress filters.

type Outcome = "all" | "accepted" | "error";
type Order = "worth" | "recent" | "posts";

export type DiscussionFilter = {
  q: string;
  tag: string;
  paper: string;
  domain: string;
  outcome: Outcome;
  mine: boolean; // only threads where I can share my review
  order: Order;
};

const EMPTY: DiscussionFilter = {
  q: "",
  tag: "",
  paper: "",
  domain: "",
  outcome: "all",
  mine: false,
  order: "worth",
};
const KEY = "dpc.discussion-filter";

/** A link to the discussions of one hashtag (C-44). */
export const discussionTagLink = (tag: string) => ({
  href: "#/discussions",
  onClick: () => presetFilter(KEY, EMPTY, { tag }),
});

const OUTCOMES: { key: Exclude<Outcome, "all">; label: string }[] = [
  { key: "accepted", label: "Accepted" },
  { key: "error", label: "Error found" },
];

const ORDERS: { key: Order; label: string }[] = [
  { key: "worth", label: "Worth reading first" },
  { key: "recent", label: "Latest activity" },
  { key: "posts", label: "Most posts" },
];

function matches(t: ThreadSummary, f: DiscussionFilter, withOutcome: boolean): boolean {
  if (!matchesText(f.q, `${t.declaration} ${t.paper}`, t.tags)) return false;
  if (f.tag && !(t.tags ?? []).includes(f.tag)) return false;
  if (f.paper && t.paper !== f.paper) return false;
  if (f.domain && t.domain !== f.domain) return false;
  if (f.mine && !t.can_share) return false;
  if (withOutcome && f.outcome !== "all" && t.outcome !== f.outcome) return false;
  return true;
}

function ordered(list: ThreadSummary[], order: Order): ThreadSummary[] {
  const out = [...list];
  if (order === "recent") out.sort((a, b) => b.last_activity.localeCompare(a.last_activity));
  if (order === "posts") out.sort((a, b) => b.posts - a.posts);
  return out; // "worth": as the server sends them (votes, then activity)
}

export function useDiscussionFilter(list: ThreadSummary[]) {
  const [filter, setFilter] = useState<DiscussionFilter>(() => loadFilter(KEY, EMPTY));
  useEffect(() => sessionStorage.setItem(KEY, JSON.stringify(filter)), [filter]);
  const shown = useMemo(
    () =>
      ordered(
        list.filter((t) => matches(t, filter, true)),
        filter.order,
      ),
    [list, filter],
  );
  return { filter, setFilter, shown };
}

export function DiscussionFilters({
  list,
  filter,
  setFilter,
  shown,
}: {
  list: ThreadSummary[];
  filter: DiscussionFilter;
  setFilter: (f: DiscussionFilter) => void;
  shown: number;
}) {
  const set = (patch: Partial<DiscussionFilter>) => setFilter({ ...filter, ...patch });
  const tags = useMemo(() => tally(list.flatMap((t) => t.tags ?? [])), [list]);
  const papers = useMemo(() => tally(list.map((t) => t.paper)), [list]);
  const domains = useMemo(() => tally(list.map((t) => t.domain)), [list]);
  const rest = list.filter((t) => matches(t, filter, false));
  const shareable = list.filter((t) => t.can_share).length;
  const active =
    filter.q !== "" ||
    filter.tag !== "" ||
    filter.paper !== "" ||
    filter.domain !== "" ||
    filter.outcome !== "all" ||
    filter.mine;
  return (
    <section className="progress-filters" aria-label="Filter the discussions">
      <div className="filter-row">
        <input
          type="search"
          placeholder="Search, also #hashtags"
          aria-label="Search declarations, papers and hashtags"
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
        {papers.length > 1 && (
          <select
            aria-label="Paper"
            value={filter.paper}
            onChange={(e) => set({ paper: e.target.value })}
          >
            <option value="">All papers</option>
            {papers.map(([p, n]) => (
              <option key={p} value={p}>
                {p} ({n})
              </option>
            ))}
          </select>
        )}
        {domains.length > 1 && (
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
        )}
        <select
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
        <div className="segmented" role="group" aria-label="Outcome">
          <button aria-pressed={filter.outcome === "all"} onClick={() => set({ outcome: "all" })}>
            All {rest.length}
          </button>
          {OUTCOMES.map((o) => {
            const n = rest.filter((t) => t.outcome === o.key).length;
            return (
              <button
                key={o.key}
                aria-pressed={filter.outcome === o.key}
                onClick={() => set({ outcome: o.key })}
                disabled={n === 0 && filter.outcome !== o.key}
              >
                {o.label} {n}
              </button>
            );
          })}
        </div>
        {shareable > 0 && (
          <label className="small filter-check">
            <input
              type="checkbox"
              checked={filter.mine}
              onChange={(e) => set({ mine: e.target.checked })}
            />{" "}
            Only where I can share my review ({shareable})
          </label>
        )}
        <p className="muted small filter-count" aria-live="polite">
          {shown === list.length
            ? `${list.length} discussions`
            : `${shown} of ${list.length} discussions`}
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
