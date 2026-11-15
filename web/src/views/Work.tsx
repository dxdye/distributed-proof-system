import { useCallback, useEffect, useState } from "react";
import { api, type ChoiceSet, type Me } from "../api";
import { TIER_HINTS, TIER_LABELS, TierBadge } from "../components/Tier";
import { Welcome, introDone } from "../components/Welcome";
import { domainLabel, kindLabel, splitName } from "../kinds";
import { navigate } from "../router";

const ALL_TIERS = ["easy", "medium", "hard", "excellence"];

/** What the reviewer wants to work on. Preferences raise the chance that such
 * tickets are offered; they never hide the rest completely (SR-32). */
/** The difficulty preference is an upper bound ("not harder than"): stored as
 * the list of every tier up to it, which is what the server matches against. */
const tiersUpTo = (upTo: string | null): string[] =>
  upTo === null ? [] : ALL_TIERS.slice(0, ALL_TIERS.indexOf(upTo) + 1);
const upToOf = (tiers: string[]): string | null =>
  [...ALL_TIERS].reverse().find((t) => tiers.includes(t)) ?? null;

function Preferences({ me, onSaved }: { me: Me; onSaved: () => void }) {
  const [domains, setDomains] = useState<string[]>(me.preferences.domains);
  const [upTo, setUpTo] = useState<string | null>(upToOf(me.preferences.tiers));
  const tiers = tiersUpTo(upTo);
  const [known, setKnown] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const changed =
    [...domains].sort().join() !== [...me.preferences.domains].sort().join() ||
    tiers.join() !==
      [...me.preferences.tiers].sort((a, b) => ALL_TIERS.indexOf(a) - ALL_TIERS.indexOf(b)).join();
  const anySet = me.preferences.domains.length + me.preferences.tiers.length > 0;

  useEffect(() => {
    api
      .domains()
      .then(setKnown)
      .catch(() => {});
  }, []);

  const toggle = (list: string[], set: (v: string[]) => void, v: string) =>
    set(list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  async function save() {
    setError(null);
    try {
      await api.setPreferences(domains, tiers);
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <details className="prefs" open={anySet}>
      <summary>What would you like to work on?</summary>
      <p className="muted small">
        Up to half of the offered tickets match your choice, the rest is drawn at random, so that
        nobody can steer towards a particular paper. Domain and difficulty must both match. Nothing
        selected means: anything.
      </p>
      <div className="chip-row">
        <span className="chip-label">Domain</span>
        {[...new Set([...known, ...domains])].map((d) => (
          <button
            key={d}
            className="chip"
            aria-pressed={domains.includes(d)}
            onClick={() => toggle(domains, setDomains, d)}
          >
            {domainLabel(d)}
          </button>
        ))}
      </div>
      <div className="chip-row" role="group" aria-label="Difficulty up to">
        <span className="chip-label">Up to</span>
        <button className="chip" aria-pressed={upTo === null} onClick={() => setUpTo(null)}>
          Any
        </button>
        {ALL_TIERS.map((t) => {
          const open = me.tiers_open.includes(t);
          return (
            <button
              key={t}
              className={`chip tier-chip tier-${t}`}
              aria-pressed={upTo === t}
              disabled={!open}
              title={
                open ? `${TIER_LABELS[t]} and easier. ${TIER_HINTS[t]}` : `Locked. ${TIER_HINTS[t]}`
              }
              onClick={() => setUpTo(t)}
            >
              {open ? "" : "🔒 "}
              {TIER_LABELS[t]}
            </button>
          );
        })}
      </div>
      {error && <p className="error">{error}</p>}
      {changed ? (
        <button className="secondary" onClick={save}>
          Save and draw new tickets
        </button>
      ) : (
        anySet && <p className="muted small prefs-saved">✓ Saved</p>
      )}
    </details>
  );
}

/** A Lean name that may break only after a dot or an underscore, never inside
 * a word. */
function Breakable({ text, className }: { text: string; className: string }) {
  const parts = text.split(/(?<=[._])/);
  return (
    <code className={className}>
      {parts.map((p, i) => (
        <span key={i}>
          {p}
          {i < parts.length - 1 && <wbr />}
        </span>
      ))}
    </code>
  );
}

function duration(minutes: number | null): string {
  if (minutes === null) return "no time estimate yet";
  if (minutes < 90) return `expected about ${minutes} min`;
  const hours = Math.round(minutes / 60);
  return hours < 36 ? `expected about ${hours} h` : `expected about ${Math.round(hours / 24)} days`;
}

// Choice set (SR-38): a few tickets from different papers, random order, no
// popularity. Taking one is binding; it becomes a lease (SR-26). Only the expected
// duration is shown, never a countdown (SR-30).
export function Work({ me, reload }: { me: Me; reload: () => void }) {
  const [set, setSet] = useState<ChoiceSet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const draw = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      setSet(await api.choiceSet());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, []);

  // Drawn also at the limit: the set is shown, greyed out, until a ticket is
  // finished or returned (taking one still respects the limit).
  useEffect(() => {
    void draw();
  }, [draw, me.leases.length]);

  const blocked = me.leases.length >= me.wip_limit;
  const wanted = me.preferences.domains.length + me.preferences.tiers.length > 0;
  // Before any ticket of a kind has been reviewed there are no estimates: say
  // so once, not on every row (SR-30).
  const noEstimates = Boolean(set?.tickets.every((t) => t.expected_minutes === null));
  const blockedHint =
    `You already hold ${me.leases.length === 1 ? "a ticket" : `${me.leases.length} tickets`} ` +
    `(your limit is ${me.wip_limit}). Finish or return it to take this one; returning carries no penalty.`;

  async function take(ticketId: string) {
    if (!set?.set_id) return;
    try {
      const lease = await api.take(set.set_id, ticketId);
      reload();
      navigate(`/lease/${lease.lease_id}`);
    } catch (e) {
      setError((e as Error).message);
      void draw();
    }
  }

  const [dutyError, setDutyError] = useState<string | null>(null);
  async function duty() {
    setDutyError(null);
    try {
      const lease = await api.nextDuty();
      if (lease) {
        reload();
        navigate(`/lease/${lease.lease_id}`);
      } else {
        setDutyError("No re-check is waiting for you right now.");
        reload();
      }
    } catch (e) {
      setDutyError((e as Error).message);
    }
  }

  const isPvv = Object.values(me.roles).some((r) => r.includes("PVV")) || me.maintainer;
  const [intro, setIntro] = useState(() => !introDone(me));

  return (
    <div>
      {intro && <Welcome me={me} onClose={() => setIntro(false)} />}
      <section className="card">
        <h2>Your tickets</h2>
        {me.leases.length === 0 && <p className="muted">You hold no ticket right now.</p>}
        <ul className="leases">
          {me.leases.map((l) => (
            <li key={l.lease_id}>
              <a href={`#/lease/${l.lease_id}`}>
                <code>{l.ticket.view.declaration}</code>
              </a>{" "}
              <span className="badge">{l.duty}</span>{" "}
              <span className="muted">{l.ticket.paper}</span>{" "}
              <span className="muted small">· {duration(l.expected_minutes)}</span>
            </li>
          ))}
        </ul>
        <p className="muted small">
          You can hold up to {me.wip_limit} {me.wip_limit === 1 ? "ticket" : "tickets"} at a time.
          Returning a ticket carries no penalty.
          {!intro && (
            <>
              {" "}
              <button className="link small" onClick={() => setIntro(true)}>
                How a review goes
              </button>
            </>
          )}
        </p>
      </section>

      {isPvv && (
        <section className={me.pvv_waiting > 0 ? "card duty-card waiting" : "card duty-card"}>
          <div className="row">
            <div>
              <span className="eyebrow">Re-checks · PVV</span>
              <h2>
                {me.pvv_waiting === 0
                  ? "No re-check is waiting for you"
                  : `${me.pvv_waiting} ${me.pvv_waiting === 1 ? "re-check is" : "re-checks are"} waiting for you`}
              </h2>
            </div>
            <button
              onClick={duty}
              disabled={me.pvv_waiting === 0}
              title="Takes the oldest waiting re-check: a claimed error first, then a verdict to check a second time."
            >
              Start a re-check
            </button>
          </div>
          <p className="muted small">
            As a re-checker you decide errors that reviewers have claimed, and you check verdicts of
            others a second time. Re-checks are assigned in order, not chosen, so that nobody can
            pick whose verdict to check. Claimed errors come first: they hold up the decision.
          </p>
          {dutyError && <p className="error">{dutyError}</p>}
        </section>
      )}

      <section className="card">
        <h2>Choose your next ticket</h2>
        <Preferences
          me={me}
          onSaved={() => {
            reload();
            void draw();
          }}
        />
        {busy ? (
          <p className="muted">Drawing…</p>
        ) : set && set.tickets.length > 0 ? (
          <>
            {blocked ? (
              <p className="blocked-note">
                These are your next tickets. You already hold{" "}
                <a href={`#/lease/${me.leases[0].lease_id}`}>
                  <code>{me.leases[0].ticket.view.declaration}</code>
                </a>
                {me.leases.length > 1 ? ` and ${me.leases.length - 1} more` : ""}: finish or return
                it to take one of these. Returning carries no penalty.
              </p>
            ) : (
              <p className="muted small">
                Pick one. Your choice is binding: the ticket is lent to you until you submit or
                return it. You can return it at any time, without penalty.
              </p>
            )}
            {wanted && !set.preferences_applied && (
              <p className="pref-note">
                Nothing matching your choice can be offered right now; this set is drawn at random.
              </p>
            )}
            {noEstimates && (
              <p className="muted small">
                No time estimates yet: they appear once tickets like these have been reviewed.
              </p>
            )}
            {/* One ticket per row, always built the same way, for any number of tickets. */}
            <ul className="choice-list">
              {set.tickets.map((t) => {
                const { ns, short } = splitName(t.declaration);
                return (
                  <li key={t.ticket_id}>
                    <button
                      className={blocked ? "choice blocked" : "choice"}
                      aria-disabled={blocked}
                      title={blocked ? blockedHint : undefined}
                      onClick={() => (blocked ? undefined : take(t.ticket_id))}
                    >
                      <span className="choice-kind">
                        <span className="badge">{kindLabel(t.decl_kind)}</span>
                        <TierBadge tier={t.tier} />
                      </span>
                      <span className="choice-main">
                        {ns && <Breakable className="choice-ns" text={ns} />}
                        <Breakable className="choice-name" text={short} />
                        <span className="choice-paper">
                          {t.paper} · {domainLabel(t.domain)}
                          {!noEstimates && ` · ${duration(t.expected_minutes)}`}
                        </span>
                      </span>
                      {!blocked && (
                        <span className="choice-take" aria-hidden="true">
                          Take →
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </>
        ) : (
          <p className="muted">Nothing to review for you at the moment.</p>
        )}
        {error && <p className="error">{error}</p>}
      </section>
    </div>
  );
}
