"""Paper passages proposed and confirmed by four eyes (proposal C-42, SR-24)."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_progress import planted_env

from dpc.coord import Conflict, CoordError, Forbidden


@pytest.mark.req("SR-24", "SR-06")
def test_a_passage_needs_a_proposal_and_a_confirmation(tmp_path: Path) -> None:
    env = planted_env(tmp_path)  # four declarations, one with a planted copy
    sid = next(iter(env.coord.state.submissions))
    planted = next(t for t in env.coord.state.tickets.values()
                   if env.vault.is_honeypot(t.ticket_id))
    decl = planted.view.declaration
    a, b = (env.maintainer(env.people(1, name)[0]) for name in ("anna", "bert"))
    stranger = env.people(1, "stranger")[0]
    with pytest.raises(Forbidden, match="PVVs and maintainers"):
        env.coord.propose_passage(stranger, sid, decl, locator="Thm 1",
                                  statement="For every n, P(n) holds.")
    with pytest.raises(CoordError, match="locator and a statement"):
        env.coord.propose_passage(a, sid, decl, locator="Thm 1", statement="short")
    pid = env.coord.propose_passage(a, sid, decl, locator="Theorem 2, p. 3",
                                    statement="For every $n$, $P(n)$ holds.")
    assert (sid, decl) in env.coord.state.seen_units[a]  # mapping means reading the original
    with pytest.raises(Forbidden, match="four eyes"):
        env.coord.decide_passage(a, pid, confirm=True)
    with pytest.raises(CoordError, match="say why"):
        env.coord.decide_passage(b, pid, confirm=False, reason="no")
    env.coord.decide_passage(b, pid, confirm=True)
    copies = env.coord.unit_tickets(sid, decl)
    assert len(copies) == 2  # the original and its planted copy show the same passage
    assert all(t.paper is not None and t.paper.locator == "Theorem 2, p. 3" for t in copies)
    assert copies[0].paper is not None and a in copies[0].paper.mapped_by \
        and b in copies[0].paper.mapped_by
    with pytest.raises(Conflict, match="no open proposal"):
        env.coord.decide_passage(b, pid, confirm=True)
    # The state comes from the log alone.
    assert all(t.paper is not None for t in env.make().unit_tickets(sid, decl))
    env.log.close()
    env.vault.close()


def test_a_reviewed_declaration_keeps_its_passage(tmp_path: Path) -> None:
    env = planted_env(tmp_path)
    sid = next(iter(env.coord.state.submissions))
    rid = env.people(1)[0]
    lease = env.take(rid)
    ticket = env.coord.state.tickets[env.coord.state.leases[lease].ticket_id]
    env.clock.advance(minutes=20)
    env.coord.submit_review(rid, lease, verdict="correct")
    a = env.maintainer(env.people(1, "anna")[0])
    with pytest.raises(Conflict, match="reviews already"):
        env.coord.propose_passage(a, sid, ticket.view.declaration, locator="Theorem 2",
                                  statement="For every $n$, $P(n)$ holds.")
    env.log.close()
    env.vault.close()
