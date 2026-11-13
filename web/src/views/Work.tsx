import { useCallback, useEffect, useState } from "react";
import { api, type ChoiceSet, type Me } from "../api";
import { TIER_HINTS, TIER_LABELS, TierBadge } from "../components/Tier";
import { navigate } from "../router";

const ALL_TIERS = ["easy", "medium", "hard", "excellence"];

/** What the reviewer wants to work on. Preferences raise the chance that such
 * tickets are offered; they never hide the rest completely (SR-32). */
function Preferences({ me, onSaved }: { me: Me; onSaved: () => void }) {
  const [domains, setDomains] = useState<string[]>(me.preferences.domains);
  const [tiers, setTiers] = useState<string[]>(me.preferences.tiers);
  const [known, setKnown] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const changed =
    domains.join() !== me.preferences.domains.join() ||
    tiers.join() !== me.preferences.tiers.join();

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
    <details
      className="prefs"
      open={me.preferences.domains.length + me.preferences.tiers.length > 0}
    >
      <summary>What would you like to work on?</summary>
      <p className="muted small">
        Tickets matching your choice are offered first; others fill up the rest. Nothing selected
        means: anything.
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
            {d}
          </button>
        ))}
      </div>
      <div className="chip-row">
        <span className="chip-label">Difficulty</span>
        {ALL_TIERS.map((t) => {
          const open = me.tiers_open.includes(t);
          return (
            <button
              key={t}
              className={`chip tier-chip tier-${t}`}
              aria-pressed={tiers.includes(t)}
              disabled={!open}
              title={open ? TIER_HINTS[t] : `Locked. ${TIER_HINTS[t]}`}
              onClick={() => toggle(tiers, setTiers, t)}
            >
              {open ? "" : "🔒 "}
              {TIER_LABELS[t]}
            </button>
          );
        })}
      </div>
      {error && <p className="error">{error}</p>}
      <button className="secondary" disabled={!changed} onClick={save}>
        Save and draw new tickets
      </button>
    </details>
  );
}

function duration(minutes: number): string {
  if (minutes < 90) return `about ${minutes} min`;
  const hours = Math.round(minutes / 60);
  return hours < 36 ? `about ${hours} h` : `about ${Math.round(hours / 24)} days`;
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

  useEffect(() => {
    if (me.leases.length < me.wip_limit) void draw();
  }, [draw, me.leases.length, me.wip_limit]);

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

  async function duty() {
    setError(null);
    try {
      const lease = await api.nextDuty();
      if (lease) {
        reload();
        navigate(`/lease/${lease.lease_id}`);
      } else setError("No PVV duty is waiting for you right now.");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const isPvv = Object.values(me.roles).some((r) => r.includes("PVV")) || me.maintainer;

  return (
    <div>
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
              <span className="muted small">· expected {duration(l.expected_minutes)}</span>
            </li>
          ))}
        </ul>
        <p className="muted small">
          You can hold up to {me.wip_limit} {me.wip_limit === 1 ? "ticket" : "tickets"} at a time.
          Returning a ticket carries no penalty.
        </p>
      </section>

      <section className="card">
        <div className="row">
          <h2>Choose your next ticket</h2>
          {isPvv && (
            <button className="secondary" onClick={duty}>
              Take next PVV duty
            </button>
          )}
        </div>
        <Preferences
          me={me}
          onSaved={() => {
            reload();
            void draw();
          }}
        />
        {me.leases.length >= me.wip_limit ? (
          <p className="muted">Finish or return a ticket first.</p>
        ) : busy ? (
          <p className="muted">Drawing…</p>
        ) : set && set.tickets.length > 0 ? (
          <>
            <p className="muted small">
              Pick one — your choice is binding: the ticket is lent to you until you submit or
              return it.
            </p>
            <div className="cards">
              {set.tickets.map((t) => (
                <button key={t.ticket_id} className="choice" onClick={() => take(t.ticket_id)}>
                  <span className="card-badges">
                    <span className="badge">{t.decl_kind}</span>
                    <TierBadge tier={t.tier} />
                  </span>
                  <code className="choice-name">{t.declaration}</code>
                  <span className="muted small">{t.paper}</span>
                  <span className="muted small">
                    {t.domain} · expected {duration(t.expected_minutes)}
                  </span>
                </button>
              ))}
            </div>
          </>
        ) : (
          <p className="muted">Nothing to review for you at the moment.</p>
        )}
        {error && <p className="error">{error}</p>}
      </section>
    </div>
  );
}
