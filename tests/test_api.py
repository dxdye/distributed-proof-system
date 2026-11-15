"""HTTP API of the coordination service (offline, FastAPI TestClient)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dpc.api import create_app

from test_coord import Env, params, specs


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    e = Env(tmp_path, params())
    yield e
    e.log.close()
    e.vault.close()


@pytest.fixture
def client(env: Env) -> TestClient:
    return TestClient(create_app(env.coord, tick_seconds=None))


def register(client: TestClient, name: str) -> dict[str, str]:
    r = client.post("/api/register", json={"pseudonym": name, "notice_acknowledged": True})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.mark.req("SR-49")
def test_registration_shows_the_notice_and_requires_it(client: TestClient) -> None:
    assert "train" in client.get("/api/notice").json()["text"]
    r = client.post("/api/register", json={"pseudonym": "bob"})
    assert r.status_code == 403
    assert client.get("/api/me").status_code == 401
    me = client.get("/api/me", headers=register(client, "bob")).json()
    assert me["pseudonym"] == "bob" and me["leases"] == []


@pytest.mark.req("SR-21", "SR-30", "SR-06")
def test_review_round_trip_without_countdown_or_honeypot_fields(env: Env,
                                                                client: TestClient) -> None:
    env.coord.open_submission(title="Paper", repo_url="https://x/p", commit="c" * 40,
                              tickets=specs("P", 3))
    auth = register(client, "carol")
    cs = client.post("/api/choice-set", headers=auth).json()
    assert len(cs["tickets"]) == 3
    assert set(cs["tickets"][0]) == {"ticket_id", "declaration", "decl_kind", "domain", "tier",
                                     "paper", "expected_minutes"}  # no popularity (SR-38)
    lease = client.post("/api/leases", headers=auth, json={
        "set_id": cs["set_id"], "ticket_id": cs["tickets"][1]["ticket_id"]}).json()
    text = json.dumps(lease)
    assert "expire" not in text and "honeypot" not in text  # SR-30, SR-06
    assert lease["ticket"]["view"]["components"][0]["target"] == "type"
    assert lease["ticket"]["questions"][0]["id"] == "fidelity"
    lid = lease["lease_id"]
    r = client.post(f"/api/leases/{lid}/review", headers=auth, json={"verdict": "incorrect"})
    assert r.status_code == 400 and "SR-09" in r.json()["detail"]
    env.clock.advance(minutes=20)
    r = client.post(f"/api/leases/{lid}/review", headers=auth, json={
        "verdict": "incorrect", "reason": "the hypotheses are vacuous for every n",
        "failed": ["vacuity"], "evidence": "example : False := sorry",
        "evidence_kind": "vacuity", "ai_used": True, "ai_provider": "some-assistant"})
    assert r.status_code == 200, r.text
    assert len(env.events("claim.opened")) == 1
    review = env.events("review.submitted")[0]
    assert review["ai"] == {"used": True, "provider": "some-assistant"}  # SR-48
    digest = review["evidence"]["file_sha256"]  # type: ignore[index]
    assert client.get(f"/api/blobs/{digest}", headers=auth).text == "example : False := sorry"
    me = client.get("/api/me", headers=auth).json()
    assert me["history"][0]["verdict"] == "incorrect" and me["history"][0]["planted_error"] is None


def test_maintainer_endpoints_are_guarded(env: Env, client: TestClient) -> None:
    sid = env.coord.open_submission(title="Paper", repo_url="https://x/p", commit="c" * 40,
                                    tickets=specs("P", 2))
    auth = register(client, "dave")
    assert client.post("/api/admin/tick", headers=auth).status_code == 403
    env.coord.appoint_maintainer(env.vault.reviewer_for_pseudonym("dave") or "")
    assert client.post("/api/admin/tick", headers=auth).json() == {"expired": 0, "revealed": 0}
    subs = client.get("/api/admin/submissions", headers=auth).json()
    assert subs[0]["tickets"] == {"open": 2}
    assert client.post(f"/api/admin/submissions/{sid}/close", headers=auth).status_code == 200
    stats = client.get("/api/stats").json()
    assert stats["submissions"] == 1 and stats["audit_head"]
    assert client.get("/api/audit/head").json()["length"] == len(env.log)


def test_claim_duty_shows_the_finding_to_the_pvv(env: Env, client: TestClient) -> None:
    env.coord.open_submission(title="Paper", repo_url="https://x/p", commit="c" * 40,
                              tickets=specs("P", 1))
    finder = register(client, "erin")
    admin = register(client, "admin")
    env.coord.appoint_maintainer(env.vault.reviewer_for_pseudonym("admin") or "")
    cs = client.post("/api/choice-set", headers=finder).json()
    lid = client.post("/api/leases", headers=finder, json={
        "set_id": cs["set_id"], "ticket_id": cs["tickets"][0]["ticket_id"]}).json()["lease_id"]
    client.post(f"/api/leases/{lid}/review", headers=finder,
                json={"verdict": "incorrect", "reason": "the bound should be strict, not ≤",
                      "failed": ["fidelity", "edge_cases"]})
    duty = client.post("/api/duties/next", headers=admin).json()
    assert duty["duty"] == "claim"
    assert duty["claim"]["reason"] == "the bound should be strict, not ≤"
    assert duty["claim"]["failed"] == ["fidelity", "edge_cases"]
    r = client.post(f"/api/leases/{duty['lease_id']}/claim", headers=admin,
                    json={"confirmed": True, "reason": "agreed"})
    assert r.status_code == 200
    history = client.get("/api/me", headers=finder).json()["history"]
    assert history[0]["outcome"] == "error"


@pytest.mark.req("SR-32")
def test_preferences_can_be_given_at_sign_up(env: Env, client: TestClient) -> None:
    """Optional, and never a qualification (C-32); the domains are public."""
    env.coord.open_submission(title="Paper", repo_url="https://x/p", commit="c" * 40,
                              tickets=specs("P", 2))
    assert client.get("/api/domains").json() == ["analysis"]
    r = client.post("/api/register", json={"pseudonym": "dora", "notice_acknowledged": True,
                                           "domains": ["analysis"]})
    assert r.status_code == 200, r.text
    me = client.get("/api/me", headers={"Authorization": f"Bearer {r.json()['token']}"}).json()
    assert me["preferences"] == {"domains": ["analysis"], "tiers": []}


@pytest.mark.req("SR-38")
def test_a_reached_limit_is_reported_with_its_time_not_as_an_error(env: Env,
                                                                   client: TestClient) -> None:
    """C-32: the client says when the next set comes, and how many changes of
    preferences are left."""
    env.coord.open_submission(title="Paper", repo_url="https://x/p", commit="c" * 40,
                              tickets=specs("P", 12))
    auth = register(client, "erin")
    me = client.get("/api/me", headers=auth).json()
    assert me["preference_changes_left"] == 3 and me["preference_change_at"] is None
    for _ in range(env.params.max_unused_sets_per_day):
        assert client.post("/api/choice-set", headers=auth).json()["tickets"]
        env.clock.advance(seconds=env.params.choice_set_ttl_s + 1)
    r = client.post("/api/choice-set", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["tickets"] == [] and body["limit"]["reason"] == "unused"
    assert body["limit"]["until"] > body["limit"]["until"][:10]  # an ISO time
