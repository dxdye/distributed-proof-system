import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  api,
  type ContextUnit,
  type GlossaryEntry,
  type LeaseContext,
  type UnitView,
} from "../api";
import { kindLabel, splitName } from "../kinds";
import { Infoview } from "./Infoview";
import { ReliesOn } from "./ReliesOn";
import { UnfoldContext } from "./unfoldContext";

// What a ticket builds on and what uses it (concept §3, §8.8, SR-21; C-39):
// the other class-A declarations of the paper, unfolded on request, down to
// Lean and Mathlib. Only declarations of TCB_new appear: definitions,
// structures and the main theorem's statement, never a proven lemma that
// mentions one (a planted copy would show against it).
//
// Every person sees every declaration in one version: the one of their own
// ticket, a planted copy included, otherwise the original; a declaration
// unfolded in the original is then not offered to them as a ticket.
//
// Presentation ("focus instead of a stack"): the page keeps the statement in
// view; a declaration opens in a sheet that slides up from below, with the
// path that led there, one at a time, and what is already seen is marked.

type Unfolded = { view: UnitView; relies_on: GlossaryEntry[] };

type State = {
  ctx: LeaseContext | null;
  units: Map<string, ContextUnit>;
  /** The opened declarations, outermost first; the last one is shown. */
  trail: string[];
  open: (declaration: string, from?: "statement" | "panel") => void;
  jump: (index: number) => void;
  close: () => void;
};

/** Loads the context of the ticket and holds the side panel; wraps the "Lean
 * says" block, so that names in the statement open the panel too. */
export function TicketContextProvider({
  leaseId,
  children,
}: {
  leaseId: string;
  children: ReactNode;
}) {
  const [ctx, setCtx] = useState<LeaseContext | null>(null);
  const [trail, setTrail] = useState<string[]>([]);
  const [cache, setCache] = useState<Record<string, Unfolded>>({});
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .leaseContext(leaseId)
      .then(setCtx)
      .catch(() => setCtx(null));
  }, [leaseId]);
  const units = useMemo(() => new Map((ctx?.units ?? []).map((u) => [u.declaration, u])), [ctx]);

  const load = useCallback(
    async (declaration: string) => {
      if (cache[declaration]) return true;
      try {
        const shown = await api.unfold(leaseId, declaration);
        setCache((c) => ({ ...c, [declaration]: shown }));
        // Unfolding counts as seen (C-39): mark it here as the server does.
        setCtx(
          (c) =>
            c && {
              ...c,
              units: c.units.map((u) => (u.declaration === declaration ? { ...u, seen: true } : u)),
            },
        );
        return true;
      } catch (e) {
        setError((e as Error).message);
        return false;
      }
    },
    [cache, leaseId],
  );

  const open = useCallback(
    (declaration: string, from: "statement" | "panel" = "panel") => {
      setError(null);
      void load(declaration).then((ok) => {
        if (!ok) return;
        setTrail((t) => {
          if (from === "statement" || t.length === 0) return [declaration];
          const at = t.indexOf(declaration);
          return at >= 0 ? t.slice(0, at + 1) : [...t, declaration];
        });
      });
    },
    [load],
  );
  const close = useCallback(() => setTrail([]), []);
  const jump = useCallback((index: number) => setTrail((t) => t.slice(0, index + 1)), []);

  // The page gets room at its end for the sheet; Escape closes it.
  const isOpen = trail.length > 0;
  useEffect(() => {
    document.body.classList.toggle("ctx-panel-open", isOpen);
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.classList.remove("ctx-panel-open");
    };
  }, [isOpen, close]);

  const unfold = useMemo(
    () => ({
      has: (d: string) => units.has(d) && d !== ctx?.own,
      open,
    }),
    [units, ctx?.own, open],
  );
  const state: State = { ctx, units, trail, open, jump, close };
  const current = trail[trail.length - 1];
  return (
    <UnfoldContext.Provider value={unfold}>
      <StateContext.Provider value={state}>
        {children}
        {isOpen && current && (
          <Panel state={state} shown={cache[current]} error={error} ownName={ctx?.own ?? ""} />
        )}
      </StateContext.Provider>
    </UnfoldContext.Provider>
  );
}

const StateContext = createContext<State | null>(null);

/** One compact row: kind, name (namespace quiet), main theorem, seen. */
function Row({ unit, state }: { unit: ContextUnit; state: State }) {
  const { ns, short } = splitName(unit.declaration);
  const current = state.trail[state.trail.length - 1] === unit.declaration;
  return (
    <li>
      <button
        className={current ? "ctx-row current" : "ctx-row"}
        aria-current={current ? "true" : undefined}
        onClick={() => !unit.own && state.open(unit.declaration, "statement")}
        disabled={unit.own}
        title={unit.own ? "The declaration of this ticket" : unit.declaration}
      >
        <span className="ctx-kind">{kindLabel(unit.decl_kind)}</span>
        <code>
          {ns && <span className="ctx-ns">{ns}.</span>}
          <span className="ctx-short">{short}</span>
        </code>
        {unit.declaration === state.ctx?.root && (
          <span className="badge ctx-main">main theorem</span>
        )}
        {unit.own ? (
          <span className="badge">this ticket</span>
        ) : (
          unit.seen && (
            <span className="ctx-seen" title="You have seen this declaration">
              seen
            </span>
          )
        )}
        {!unit.own && (
          <span className="ctx-open" aria-hidden="true">
            ›
          </span>
        )}
      </button>
    </li>
  );
}

/** The declarations below the main theorem, as an indented tree; each one
 * once (a repeated one points up). */
function Tree({ state }: { state: State }) {
  const { ctx, units } = state;
  if (!ctx) return null;
  const placed = new Set<string>();
  const node = (d: string, depth: number): ReactNode => {
    const unit = units.get(d);
    if (!unit) return null;
    const again = placed.has(d);
    placed.add(d);
    const kids = again || depth > 8 ? [] : unit.depends_on.filter((k) => units.has(k));
    return (
      <li key={`${d}:${depth}`} className={again ? "ctx-again" : undefined}>
        <ul className="ctx-rows">
          <Row unit={unit} state={state} />
        </ul>
        {again ? (
          <span className="muted small ctx-again-note">(shown above)</span>
        ) : (
          kids.length > 0 && <ul className="ctx-tree">{kids.map((k) => node(k, depth + 1))}</ul>
        )}
      </li>
    );
  };
  const start = ctx.root && units.has(ctx.root) ? [ctx.root] : [];
  const tree = start.map((d) => node(d, 0));
  const rest = ctx.units.filter((u) => !placed.has(u.declaration));
  return (
    <>
      <ul className="ctx-tree ctx-tree-top">{tree}</ul>
      {rest.length > 0 && (
        <ul className="ctx-rows">
          {rest.map((u) => (
            <Row key={u.declaration} unit={u} state={state} />
          ))}
        </ul>
      )}
    </>
  );
}

/** The sheet from below: the path, the declaration, what it builds on. */
function Panel({
  state,
  shown,
  error,
  ownName,
}: {
  state: State;
  shown: Unfolded | undefined;
  error: string | null;
  ownName: string;
}) {
  const current = state.trail[state.trail.length - 1];
  const unit = state.units.get(current);
  const { ns, short } = splitName(current);
  // Names in the panel go one level deeper instead of starting a new path.
  const outer = useContext(UnfoldContext);
  const deeper = useMemo(
    () => outer && { has: outer.has, open: (d: string) => state.open(d, "panel") },
    [outer, state],
  );
  const below = (unit?.depends_on ?? []).filter(
    (d) => d !== ownName && !state.trail.includes(d) && state.units.has(d),
  );
  return (
    <aside className="ctx-panel" aria-label="Unfolded declaration">
      <div className="ctx-panel-head">
        <nav className="ctx-path" aria-label="Path">
          <button className="link" onClick={state.close}>
            Statement
          </button>
          {state.trail.map((d, i) => (
            <span key={d}>
              <span className="ctx-path-sep" aria-hidden="true">
                ›
              </span>
              {i === state.trail.length - 1 ? (
                <b>{splitName(d).short}</b>
              ) : (
                <button className="link" onClick={() => state.jump(i)}>
                  {splitName(d).short}
                </button>
              )}
            </span>
          ))}
        </nav>
        <button className="ctx-panel-close" onClick={state.close} aria-label="Close">
          ✕
        </button>
      </div>
      <div className="ctx-panel-body">
        <div className="ctx-panel-title">
          <span className="ctx-kind">{unit ? kindLabel(unit.decl_kind) : ""}</span>
          <code>
            {ns && <span className="ctx-ns">{ns}.</span>}
            <b>{short}</b>
          </code>
          {current === state.ctx?.root && <span className="badge ctx-main">main theorem</span>}
        </div>
        {error && <p className="error small">{error}</p>}
        {shown ? (
          <>
            <UnfoldContext.Provider value={deeper}>
              <Infoview view={shown.view} hideContext compact />
            </UnfoldContext.Provider>
            <ReliesOn entries={shown.relies_on} conventionsOnly />
            {below.length > 0 && (
              <>
                <p className="ctx-label">Builds on</p>
                <ul className="ctx-rows">
                  {below.map((d) => {
                    const u = state.units.get(d)!;
                    return (
                      <li key={d}>
                        <button
                          className="ctx-row"
                          onClick={() => state.open(d, "panel")}
                          title={d}
                        >
                          <span className="ctx-kind">{kindLabel(u.decl_kind)}</span>
                          <code>
                            <span className="ctx-short">{splitName(d).short}</span>
                          </code>
                          {u.seen && <span className="ctx-seen">seen</span>}
                          <span className="ctx-open" aria-hidden="true">
                            ›
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </>
            )}
            {state.trail.length > 1 && (
              <button className="link ctx-back" onClick={() => state.jump(state.trail.length - 2)}>
                ← back to {splitName(state.trail[state.trail.length - 2]).short}
              </button>
            )}
          </>
        ) : (
          !error && <p className="muted small">Loading…</p>
        )}
      </div>
    </aside>
  );
}

/** The lists under the statement: what it builds on, what uses it, all of
 * the formalization as a tree, and how much of it was looked at. */
export function TicketContext() {
  const state = useContext(StateContext);
  if (!state?.ctx || state.ctx.units.length <= 1) return null;
  const { ctx, units } = state;
  const own = units.get(ctx.own);
  if (!own) return null;
  const rows = (names: string[]) => (
    <ul className="ctx-rows">
      {names
        .filter((d) => units.has(d))
        .map((d) => (
          <Row key={d} unit={units.get(d)!} state={state} />
        ))}
    </ul>
  );
  const others = ctx.units.filter((u) => !u.own);
  const seen = others.filter((u) => u.seen).length;
  return (
    <section className="ticket-context" aria-label="Context of this declaration">
      <h4>Builds on</h4>
      {own.depends_on.length > 0 ? (
        rows(own.depends_on)
      ) : (
        <p className="muted small">Only Lean and Mathlib.</p>
      )}
      {own.used_by.length > 0 && (
        <>
          <h4>Used by</h4>
          {rows(own.used_by)}
        </>
      )}
      <details className="ctx-map">
        <summary>
          All {ctx.units.length} declarations of this formalization · {seen} of {others.length}{" "}
          looked at
        </summary>
        <Tree state={state} />
      </details>
      <p className="muted small">
        A declaration opens in a sheet from below, with the path that led there; names in the
        statement open the same way. Once you have seen one, it is not offered to you as a ticket of
        its own.
      </p>
    </section>
  );
}
