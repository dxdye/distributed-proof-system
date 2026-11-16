import { useCallback, useEffect, useState } from "react";
import { api, type PassageProposal } from "../api";
import { MathText } from "./MathText";

// Mapping a paper passage by four eyes (proposal C-42): a PVV or maintainer of
// the domain proposes, another maintainer confirms. Possible only while nobody
// has reviewed the declaration; the confirmed passage is shown on every ticket
// of it, planted copies included.

const STATUS: Record<string, string> = {
  open: "waiting for a second maintainer",
  confirmed: "confirmed",
  rejected: "rejected",
};

export function PassageMapping({
  sid,
  decl,
  canConfirm,
  onChanged,
}: {
  sid: string;
  decl: string;
  canConfirm: boolean;
  onChanged: () => void;
}) {
  const [list, setList] = useState<PassageProposal[]>([]);
  const [form, setForm] = useState({ locator: "", statement: "", note: "" });
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(() => {
    api.passages(sid, decl).then(setList, () => setList([]));
  }, [sid, decl]);
  useEffect(load, [load]);
  const run = async (action: () => Promise<unknown>, done: string) => {
    try {
      await action();
      setMessage(done);
      load();
      onChanged();
    } catch (e) {
      setMessage((e as Error).message);
    }
  };
  return (
    <section className="card passage-mapping">
      <h3>Paper passage: propose and confirm</h3>
      <p className="muted small">
        Four eyes: a PVV or maintainer of the domain proposes, another maintainer confirms. Only
        while nobody has reviewed this declaration, so that every verdict compares with the same
        passage. Write the statement in your own words or quote it, with formulas in $…$.
      </p>
      {list.length > 0 && (
        <ul className="proposals">
          {list.map((p) => (
            <li key={p.proposal_id} className={`proposal proposal-${p.status}`}>
              <div className="small">
                <b>{p.locator}</b> · {STATUS[p.status] ?? p.status}
                {p.mine && " · your proposal"}
                {p.reason && ` · ${p.reason}`}
              </div>
              <p>
                <MathText text={p.statement} />
              </p>
              {p.note && <p className="small muted">{p.note}</p>}
              {p.status === "open" && canConfirm && !p.mine && (
                <div className="row">
                  <button
                    onClick={() =>
                      run(
                        () => api.decidePassage(p.proposal_id, true, ""),
                        "Confirmed: every ticket of this declaration shows it now.",
                      )
                    }
                  >
                    Confirm
                  </button>
                  <input
                    placeholder="Why not (for a rejection)"
                    value={reasons[p.proposal_id] ?? ""}
                    onChange={(e) => setReasons({ ...reasons, [p.proposal_id]: e.target.value })}
                  />
                  <button
                    className="secondary"
                    disabled={(reasons[p.proposal_id] ?? "").trim().length < 10}
                    onClick={() =>
                      run(
                        () => api.decidePassage(p.proposal_id, false, reasons[p.proposal_id]),
                        "Rejected.",
                      )
                    }
                  >
                    Reject
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="propose-form">
        <input
          placeholder="Where in the paper, e.g. Theorem 1.1, p. 2"
          aria-label="Locator"
          value={form.locator}
          onChange={(e) => setForm({ ...form, locator: e.target.value })}
        />
        <textarea
          rows={4}
          placeholder="What the paper states there; formulas in $…$"
          aria-label="Statement"
          value={form.statement}
          onChange={(e) => setForm({ ...form, statement: e.target.value })}
        />
        {form.statement.trim() && (
          <p className="propose-preview">
            <MathText text={form.statement} />
          </p>
        )}
        <input
          placeholder="Note (optional), e.g. paraphrase or quote"
          aria-label="Note"
          value={form.note}
          onChange={(e) => setForm({ ...form, note: e.target.value })}
        />
        <button
          disabled={!form.locator.trim() || form.statement.trim().length < 10}
          onClick={() =>
            run(
              () => api.proposePassage(sid, decl, form.locator, form.statement, form.note),
              "Proposed. Another maintainer of the domain confirms it.",
            ).then(() => setForm({ locator: "", statement: "", note: "" }))
          }
        >
          Propose
        </button>
      </div>
      {message && <p className="muted small">{message}</p>}
    </section>
  );
}
