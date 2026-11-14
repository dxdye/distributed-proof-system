import { useEffect, useState } from "react";
import { api, type Lease, type ReviewInput } from "../api";
import { Infoview } from "../components/Infoview";
import { Reference } from "../components/Reference";
import { ReliesOn } from "../components/ReliesOn";
import { TierBadge } from "../components/Tier";
import { navigate } from "../router";

/** Short labels of the checklist questions (the full text is in the ticket). */
export const QUESTION_LABELS: Record<string, string> = {
  fidelity: "Not what the paper says",
  junk_values: "Junk values",
  edge_cases: "Edge cases",
  vacuity: "Vacuous or trivial",
  quantifiers: "Quantifiers or types",
};

const EVIDENCE_KINDS = [
  ["vacuity", "Vacuity: the hypotheses cannot hold together"],
  ["trivialization", "Trivialisation: the statement holds for a trivial reason"],
  ["definition_test_counterexample", "A definition fails a test it should pass"],
] as const;

function ReviewForm({ lease, onDone }: { lease: Lease; onDone: () => void }) {
  const [verdict, setVerdict] = useState<"correct" | "incorrect" | null>(null);
  const [reason, setReason] = useState("");
  const [failed, setFailed] = useState<string[]>([]);
  const [withEvidence, setWithEvidence] = useState(false);
  const [evidence, setEvidence] = useState("");
  const [kind, setKind] = useState<string>("vacuity");
  const [aiUsed, setAiUsed] = useState(false);
  const [provider, setProvider] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!verdict) return;
    const body: ReviewInput = {
      verdict,
      reason,
      failed: verdict === "incorrect" ? failed : [],
      evidence: withEvidence && verdict === "incorrect" ? evidence : null,
      evidence_kind: withEvidence && verdict === "incorrect" ? kind : null,
      ai_used: aiUsed,
      ai_provider: aiUsed ? provider : null,
    };
    try {
      await api.review(lease.lease_id, body);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <section className="card">
      <h3>Your verdict</h3>
      <p className="muted small">Go through these questions. If one of them fails, say which.</p>
      <ul className="questions">
        {lease.ticket.questions.map((q) => (
          <li key={q.id}>{q.text}</li>
        ))}
      </ul>
      <div className="verdicts">
        <label className="inline">
          <input
            type="radio"
            checked={verdict === "correct"}
            onChange={() => setVerdict("correct")}
          />
          The formalisation is faithful
        </label>
        <label className="inline">
          <input
            type="radio"
            checked={verdict === "incorrect"}
            onChange={() => setVerdict("incorrect")}
          />
          I found a problem
        </label>
      </div>
      {verdict === "incorrect" && (
        <fieldset className="failed">
          <legend>Which question fails? (at least one)</legend>
          {lease.ticket.questions.map((q) => (
            <label key={q.id} className="inline" title={q.text}>
              <input
                type="checkbox"
                checked={failed.includes(q.id)}
                onChange={(e) =>
                  setFailed(e.target.checked ? [...failed, q.id] : failed.filter((f) => f !== q.id))
                }
              />
              {QUESTION_LABELS[q.id] ?? q.id}
            </label>
          ))}
        </fieldset>
      )}
      <label>
        Justification{" "}
        {verdict === "incorrect"
          ? `(required: what exactly is wrong, at least ${lease.min_reason_chars} characters)`
          : "(optional)"}
        <textarea rows={4} value={reason} onChange={(e) => setReason(e.target.value)} />
        {verdict === "incorrect" && (
          <span className="muted small">
            {reason.trim().length} / {lease.min_reason_chars}
          </span>
        )}
      </label>
      {verdict === "incorrect" && (
        <div className="evidence">
          <label className="inline">
            <input
              type="checkbox"
              checked={withEvidence}
              onChange={(e) => setWithEvidence(e.target.checked)}
            />
            Attach a Lean file as evidence (checked against the fixed commit)
          </label>
          {withEvidence && (
            <>
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                {EVIDENCE_KINDS.map(([k, text]) => (
                  <option key={k} value={k}>
                    {text}
                  </option>
                ))}
              </select>
              <textarea
                className="mono"
                rows={8}
                value={evidence}
                placeholder="example : ¬ ∃ x, ... := by ..."
                onChange={(e) => setEvidence(e.target.value)}
              />
            </>
          )}
        </div>
      )}
      <label className="inline">
        <input type="checkbox" checked={aiUsed} onChange={(e) => setAiUsed(e.target.checked)} />I
        used an AI assistant for this review
      </label>
      {aiUsed && (
        <input
          placeholder="Which one?"
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
        />
      )}
      {error && <p className="error">{error}</p>}
      <button
        disabled={
          !verdict ||
          (verdict === "incorrect" &&
            (failed.length === 0 || reason.trim().length < lease.min_reason_chars))
        }
        onClick={submit}
      >
        Submit review
      </button>
    </section>
  );
}

function ClaimForm({ lease, onDone }: { lease: Lease; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [evidence, setEvidence] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const claim = lease.claim!;

  useEffect(() => {
    if (claim.evidence)
      api
        .blob(claim.evidence.file_sha256)
        .then(setEvidence)
        .catch(() => {});
  }, [claim.evidence]);

  async function decide(confirmed: boolean) {
    try {
      await api.decideClaim(lease.lease_id, confirmed, reason);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <section className="card">
      <h3>Claimed problem</h3>
      <p className="muted small">
        A reviewer reported this problem. Decide whether it is real — the concrete finding, not a
        vote (concept §8.5).
      </p>
      {claim.failed && claim.failed.length > 0 && (
        <p>
          {claim.failed.map((f) => (
            <span key={f} className="badge warn">
              {QUESTION_LABELS[f] ?? f}
            </span>
          ))}
        </p>
      )}
      <blockquote>{claim.reason}</blockquote>
      {claim.evidence && (
        <>
          <p className="small">
            Evidence ({claim.evidence.kind}),{" "}
            <code>{claim.evidence.file_sha256.slice(0, 12)}…</code>
          </p>
          <pre className="term">{evidence ?? "loading…"}</pre>
        </>
      )}
      <label>
        Your justification (required)
        <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="row">
        <button disabled={!reason.trim()} onClick={() => decide(true)}>
          The problem is real
        </button>
        <button className="secondary" disabled={!reason.trim()} onClick={() => decide(false)}>
          Not a problem
        </button>
      </div>
    </section>
  );
}

export function LeaseView({ id, reload }: { id: string; reload: () => void }) {
  const [lease, setLease] = useState<Lease | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .lease(id)
      .then(setLease)
      .catch((e) => setError((e as Error).message));
  }, [id]);

  function done() {
    reload();
    navigate("/work");
  }

  if (error) return <p className="error">{error}</p>;
  if (!lease) return <p className="muted">Loading…</p>;
  const t = lease.ticket;
  const active = lease.status === "active";

  return (
    <div className="lease">
      <section className="card">
        <div className="row">
          <div>
            <h2>{t.paper}</h2>
            <p className="muted small">
              <TierBadge tier={t.tier} /> {t.domain} · <a href={t.repo_url}>{t.repo_url}</a> @{" "}
              <code>{t.commit.slice(0, 12)}</code>
            </p>
          </div>
          {active && (
            <div className="toolbar">
              {lease.extendable && (
                <button
                  className="secondary small"
                  onClick={() =>
                    api.extend(lease.lease_id).then(setLease, (e) => setError(e.message))
                  }
                >
                  Need more time
                </button>
              )}
              <button
                className="secondary small"
                onClick={() => api.giveBack(lease.lease_id).then(done)}
              >
                Return ticket
              </button>
            </div>
          )}
        </div>
        <p className="muted small">
          {lease.expected_minutes !== null
            ? `Typical effort so far: about ${lease.expected_minutes} minutes. `
            : ""}
          There is no clock running: take the time the ticket needs.
        </p>
        {t.purpose && <p className="purpose">{t.purpose}</p>}
        <Reference
          view={t.view}
          passage={t.paper_passage}
          paperRef={t.paper_ref}
          leaseId={lease.lease_id}
          contested={t.mapping_contested_by_me}
          minChars={lease.min_reason_chars}
          active={active}
        />
        <section className="lean-panel">
          <h3>Lean says</h3>
          <Infoview view={t.view} />
          <ReliesOn entries={t.relies_on} />
        </section>
      </section>
      {active && lease.duty === "claim" && <ClaimForm lease={lease} onDone={done} />}
      {active && lease.duty !== "claim" && <ReviewForm lease={lease} onDone={done} />}
      {!active && <p className="muted">This lease is {lease.status}.</p>}
    </div>
  );
}
