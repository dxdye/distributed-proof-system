import { useCallback, useEffect, useState } from "react";
import { api, type MaintainerDeclaration, type Me } from "../api";
import { PassageMapping } from "../components/PassageMapping";
import { domainLabel, kindLabel } from "../kinds";
import { Infoview } from "../components/Infoview";
import { ReliesOn } from "../components/ReliesOn";
import { Reference } from "../components/Reference";
import { TierBadge } from "../components/Tier";
import { threadHref } from "./Discussions";
import { progressHref } from "./Progress";

// A declaration as its reviewers see it, for maintainers and PVVs of its
// domain (from the progress page), and where its paper passage is mapped by
// four eyes (C-42). Not public: the real statement next to a planted copy
// would give the copy away; opening it counts as having seen the original.

const STATE_LABELS: Record<string, string> = {
  accepted: "accepted",
  error: "error found",
  "in review": "in review",
  "not started": "not started",
};

export function DeclarationView({ sid, decl, me }: { sid: string; decl: string; me: Me }) {
  const [d, setD] = useState<MaintainerDeclaration | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    api.admin.declaration(sid, decl).then(setD, (e) => setError((e as Error).message));
  }, [sid, decl]);
  useEffect(load, [load]);

  if (error) return <p className="error">{error}</p>;
  if (!d) return <p className="muted">Loading…</p>;
  return (
    <div>
      <section className="card">
        <p className="small">
          <a href={progressHref(sid)}>← {d.paper}</a>
        </p>
        <div className="progress-card-head">
          <h2>
            <code>{d.declaration}</code>
          </h2>
          <span className="badge">{kindLabel(d.decl_kind)}</span>
          <TierBadge tier={d.tier} />
          <span className={`badge state-${d.state.replace(" ", "-")}`}>
            {STATE_LABELS[d.state] ?? d.state}
          </span>
        </div>
        <p className="muted small">
          {domainLabel(d.domain)} · <a href={d.repo_url}>{d.repo_url}</a> @{" "}
          <code>{d.commit.slice(0, 12)}</code>
          {d.decided_at &&
            ` · decided ${new Date(d.decided_at).toLocaleDateString("en", { dateStyle: "medium" })}`}
          {d.contested > 0 &&
            ` · paper passage contested by ${d.contested} ${d.contested === 1 ? "reviewer" : "reviewers"}`}
        </p>
        <p className="maintainer-note small">
          The ticket as its reviewers see it. Only maintainers and PVVs of the domain see
          declarations under review, because the real statement next to a planted copy would give
          the copy away. You have now seen the original: its tickets are not offered to you.
          {d.discussion && (
            <>
              {" "}
              <a href={threadHref(sid, d.declaration)}>Open the discussion →</a>
            </>
          )}
        </p>
        {d.purpose && <p className="purpose">{d.purpose}</p>}
        <Reference
          view={d.view}
          passage={d.paper_passage}
          paperRef={d.paper_ref}
          leaseId=""
          contested={false}
          minChars={30}
          active={false}
        />
        <section className="lean-panel">
          <h3>Lean says</h3>
          <Infoview view={d.view} />
          <ReliesOn entries={d.relies_on} />
        </section>
      </section>
      {d.state === "not started" && (
        <PassageMapping
          sid={sid}
          decl={d.declaration}
          canConfirm={Boolean(me.root) || me.maintains.includes(d.domain)}
          onChanged={load}
        />
      )}
      <section className="card">
        <h3>The checklist reviewers answer</h3>
        <ul className="questions">
          {d.questions.map((q) => (
            <li key={q.id}>{q.text}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
