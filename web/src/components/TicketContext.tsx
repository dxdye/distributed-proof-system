import { useEffect, useState } from "react";
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

// What a ticket builds on and what uses it (concept §3, §8.8, SR-21; C-39):
// the other class-A declarations of the paper, unfolded on request, level by
// level, down to Lean and Mathlib. Only declarations of TCB_new appear:
// definitions, structures and the main theorem's statement, never a proven
// lemma that mentions one (a planted copy would show against it).
//
// Every person sees every declaration in one version: the one of their own
// ticket, a planted copy included, otherwise the original; a declaration
// unfolded in the original is then not offered to them as a ticket.

type Unfolded = { view: UnitView; relies_on: GlossaryEntry[] };

function Unit({
  leaseId,
  unit,
  units,
  root,
  depth,
  trail,
}: {
  leaseId: string;
  unit: ContextUnit;
  units: Map<string, ContextUnit>;
  root: string | null;
  depth: number;
  /** The own declaration and the open levels above: not shown again below. */
  trail: string[];
}) {
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState<Unfolded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { ns, short } = splitName(unit.declaration);
  const below = unit.depends_on.filter((d) => !trail.includes(d) && d !== unit.declaration);

  async function toggle() {
    setError(null);
    if (!shown) {
      try {
        setShown(await api.unfold(leaseId, unit.declaration));
      } catch (e) {
        setError((e as Error).message);
        return;
      }
    }
    setOpen(!open);
  }

  return (
    <li className="ctx-unit">
      <button className="ctx-toggle" aria-expanded={open} onClick={toggle}>
        <span className="ctx-caret" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        <span className="badge">{kindLabel(unit.decl_kind)}</span>
        <code title={unit.declaration}>
          {ns && <span className="ctx-ns">{ns}.</span>}
          {short}
        </code>
        {unit.declaration === root && <span className="badge ctx-main">main theorem</span>}
      </button>
      {error && <p className="error small">{error}</p>}
      {open && shown && (
        <div className="ctx-body">
          <Infoview view={shown.view} hideContext />
          <ReliesOn entries={shown.relies_on} conventionsOnly />
          {below.length > 0 && depth < 8 && (
            <ul className="ctx-list">
              {below.map((d) => (
                <Unit
                  key={d}
                  leaseId={leaseId}
                  unit={units.get(d)!}
                  units={units}
                  root={root}
                  depth={depth + 1}
                  trail={[...trail, unit.declaration]}
                />
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

export function TicketContext({ leaseId }: { leaseId: string }) {
  const [ctx, setCtx] = useState<LeaseContext | null>(null);
  useEffect(() => {
    api
      .leaseContext(leaseId)
      .then(setCtx)
      .catch(() => setCtx(null));
  }, [leaseId]);
  if (!ctx || ctx.units.length <= 1) return null;
  const units = new Map(ctx.units.map((u) => [u.declaration, u]));
  const own = units.get(ctx.own);
  if (!own) return null;
  const list = (names: string[]) => (
    <ul className="ctx-list">
      {names.map((d) => (
        <Unit
          key={d}
          leaseId={leaseId}
          unit={units.get(d)!}
          units={units}
          root={ctx.root}
          depth={0}
          trail={[ctx.own]}
        />
      ))}
    </ul>
  );
  const others = ctx.units.filter((u) => !u.own).map((u) => u.declaration);
  return (
    <section className="ticket-context" aria-label="Context of this declaration">
      <h4>Builds on</h4>
      {own.depends_on.length > 0 ? (
        list(own.depends_on)
      ) : (
        <p className="muted small">Only Lean and Mathlib.</p>
      )}
      {own.used_by.length > 0 && (
        <>
          <h4>Used by</h4>
          {list(own.used_by)}
        </>
      )}
      <details className="ctx-map">
        <summary>All {ctx.units.length} declarations of this formalization</summary>
        {list(others)}
      </details>
      <p className="muted small">
        Unfolding shows a declaration as it stands in the submission, level by level down to Lean
        and Mathlib. Once you have seen one this way, it is not offered to you as a ticket of its
        own.
      </p>
    </section>
  );
}
