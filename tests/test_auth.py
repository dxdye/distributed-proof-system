"""Sign-in through identity providers (docs/adr/0010).

Offline tests sign their own tokens with a throwaway RSA key. The test marked
``keycloak`` talks to the development Keycloak (``pixi run keycloak-up``).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from dpc.api import create_app
from dpc.auth import (
    AuthConfig,
    Authenticator,
    AuthError,
    LocalTokenProvider,
    OidcProvider,
    build_authenticator,
    keycloak,
    load_auth_config,
)

from conftest import ROOT
from test_coord import Env, params

ISSUER = "https://login.example.org/realms/dpc"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(key: Any = KEY, alg: str = "RS256", **overrides: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {"iss": ISSUER, "aud": "dpc-api", "sub": "user-1", "iat": now,
                              "exp": now + 300, "realm_access": {"roles": []}}
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm=alg)


def provider(**kw: Any) -> OidcProvider:
    """Keycloak-style provider that checks against the throwaway key."""
    return keycloak(url="https://login.example.org", realm="dpc", client_id="dpc-web",
                    audience="dpc-api", key_resolver=lambda _: KEY.public_key(), **kw)


# ------------------------------------------------------------- tokens
def test_valid_token_gives_the_identity_and_the_maintainer_role() -> None:
    p = provider()
    plain = p.authenticate(token())
    assert (plain.provider, plain.subject, plain.maintainer) == ("keycloak", "user-1", False)
    granted = p.authenticate(token(realm_access={"roles": ["dpc-maintainer"]}))
    assert granted.maintainer is True
    assert provider(maintainer_role=None).authenticate(token()).maintainer is None


@pytest.mark.parametrize("bad, why", [
    ({"aud": "another-api"}, "Audience"),
    ({"exp": int(time.time()) - 3600}, "expired"),
    ({"sub": None}, "sub"),
    ({"iss": "https://login.example.org/realms/other"}, "issuer"),
])
def test_tokens_for_someone_else_are_rejected(bad: dict[str, Any], why: str) -> None:
    with pytest.raises(AuthError, match=why):
        provider().authenticate(token(**bad))


def test_forged_signatures_are_rejected() -> None:
    p = provider()
    with pytest.raises(AuthError, match="Signature"):
        p.authenticate(token(key=OTHER_KEY))
    unsigned = jwt.encode({"iss": ISSUER, "aud": "dpc-api", "sub": "x", "iat": 0,
                           "exp": 2**31}, None, algorithm="none")
    with pytest.raises(AuthError):
        p.authenticate(unsigned)


def test_hmac_with_the_public_key_is_rejected() -> None:
    """Algorithm confusion: an attacker signs with HS256, using the provider's
    *public* key as the shared secret. Only asymmetric algorithms are accepted,
    even if a configuration asks for HS256."""
    pem = KEY.public_key().public_bytes(serialization.Encoding.PEM,
                                        serialization.PublicFormat.SubjectPublicKeyInfo)
    p = OidcProvider(name="x", issuer=ISSUER, client_id="c", audience="dpc-api",
                     algorithms=("RS256", "HS256"), key_resolver=lambda _: pem)
    assert "HS256" not in p.algorithms

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    # Built by hand: PyJWT refuses to sign HS256 with a PEM key.
    head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(json.dumps({"iss": ISSUER, "aud": "dpc-api", "sub": "x", "iat": 0,
                           "exp": 2**31}).encode())
    sig = b64(hmac.new(pem, f"{head}.{body}".encode(), hashlib.sha256).digest())
    with pytest.raises(AuthError):
        p.authenticate(f"{head}.{body}.{sig}")


def test_credentials_go_to_the_provider_that_issued_them(tmp_path: Path) -> None:
    env = Env(tmp_path, params())
    try:
        auth = Authenticator([LocalTokenProvider(env.vault), provider()])
        assert auth.identify(token()).provider == "keycloak"
        rid, local_token = env.coord.register("alice", notice_acknowledged=True)
        assert auth.identify(local_token).subject == rid
        with pytest.raises(AuthError, match="not accepted"):
            auth.identify(token(iss="https://elsewhere.example.org"))
    finally:
        env.log.close()
        env.vault.close()


def test_configuration_file(tmp_path: Path) -> None:
    config = load_auth_config(ROOT / "config" / "auth-keycloak.json")
    assert config.local_tokens and config.providers[0].kind == "keycloak"
    env = Env(tmp_path, params())
    try:
        auth = build_authenticator(config, env.vault)
        names = [p["name"] for p in auth.public_config()["providers"]]  # type: ignore[index]
        assert names == ["local", "keycloak"]
        public = auth.public_config()["providers"][1]  # type: ignore[index]
        assert public["issuer"] == "http://localhost:8080/realms/dpc"
        assert public["client_id"] == "dpc-web"
        with pytest.raises(ValueError, match="no sign-in"):
            build_authenticator(AuthConfig(local_tokens=False), env.vault)
    finally:
        env.log.close()
        env.vault.close()


# ------------------------------------------------------------- API
@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    e = Env(tmp_path, params())
    yield e
    e.log.close()
    e.vault.close()


def client_for(env: Env, *, local: bool = True) -> TestClient:
    providers: list[Any] = [LocalTokenProvider(env.vault)] if local else []
    auth = Authenticator([*providers, provider()])
    return TestClient(create_app(env.coord, auth=auth, tick_seconds=None))


def bearer(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.req("SR-23", "SR-49")
def test_sign_in_with_an_identity_provider_then_register(env: Env) -> None:
    client = client_for(env)
    me = bearer(token(sub="kc-user-42"))
    assert client.get("/api/auth/session", headers=me).json() == {
        "authenticated": True, "provider": "keycloak", "registered": False}
    assert client.get("/api/me", headers=me).status_code == 403
    no_notice = client.post("/api/register", headers=me, json={"pseudonym": "carol"})
    assert no_notice.status_code == 403  # the notice is required here too (SR-49)
    r = client.post("/api/register", headers=me,
                    json={"pseudonym": "carol", "notice_acknowledged": True})
    assert r.status_code == 200 and "token" not in r.json()
    assert client.get("/api/auth/session", headers=me).json()["registered"] is True
    assert client.get("/api/me", headers=me).json()["pseudonym"] == "carol"
    # The log never sees the sign-in identity (SR-23).
    assert all("kc-user-42" not in str(e.payload) for e in env.log.entries())


def test_one_reviewer_per_sign_in(env: Env) -> None:
    client = client_for(env)
    me = bearer(token(sub="kc-user-7"))
    body = {"pseudonym": "dave", "notice_acknowledged": True}
    assert client.post("/api/register", headers=me, json=body).status_code == 200
    again = client.post("/api/register", headers=me, json={**body, "pseudonym": "dave2"})
    assert again.status_code == 409


def test_maintainer_role_follows_the_identity_provider(env: Env) -> None:
    client = client_for(env)
    granted = bearer(token(sub="kc-m", realm_access={"roles": ["dpc-maintainer"]}))
    client.post("/api/register", headers=granted,
                json={"pseudonym": "erin", "notice_acknowledged": True})
    assert client.get("/api/me", headers=granted).json()["maintainer"] is True
    assert client.get("/api/admin/submissions", headers=granted).status_code == 200
    revoked = bearer(token(sub="kc-m"))
    assert client.get("/api/admin/submissions", headers=revoked).status_code == 403
    assert client.get("/api/me", headers=revoked).json()["maintainer"] is False
    kinds = [e.kind for e in env.log.entries() if e.kind.startswith("reviewer.maintainer")]
    assert kinds == ["reviewer.maintainer_appointed", "reviewer.maintainer_revoked"]


def test_operator_appointments_are_kept(env: Env) -> None:
    """A maintainer appointed on the command line stays one, whatever the
    identity provider says: the provider only withdraws what it granted."""
    client = client_for(env)
    me = bearer(token(sub="kc-op"))
    r = client.post("/api/register", headers=me,
                    json={"pseudonym": "frank", "notice_acknowledged": True})
    env.coord.appoint_maintainer(r.json()["reviewer_id"])
    assert client.get("/api/me", headers=me).json()["maintainer"] is True


def test_local_tokens_can_be_switched_off(env: Env) -> None:
    _, local_token = env.coord.register("gina", notice_acknowledged=True)
    client = client_for(env, local=False)
    r = client.post("/api/register", json={"pseudonym": "hank", "notice_acknowledged": True})
    assert r.status_code == 401
    assert client.get("/api/me", headers=bearer(local_token)).status_code == 401
    kinds = [p["kind"] for p in client.get("/api/auth/config").json()["providers"]]
    assert kinds == ["oidc"]


# ------------------------------------------------------------- real Keycloak
def keycloak_token(user: str) -> str:
    r = httpx.post("http://localhost:8080/realms/dpc/protocol/openid-connect/token",
                   data={"grant_type": "password", "client_id": "dpc-test", "username": user,
                         "password": user, "scope": "openid"}, timeout=10)
    r.raise_for_status()
    return str(r.json()["access_token"])


@pytest.mark.keycloak
@pytest.mark.req("SR-23")
def test_development_keycloak_end_to_end(env: Env) -> None:
    """Tokens of the development realm: signature via the published keys,
    audience mapper, realm role for maintainers."""
    auth = Authenticator([keycloak(url="http://localhost:8080", realm="dpc",
                                   client_id="dpc-web", audience="dpc-api")])
    client = TestClient(create_app(env.coord, auth=auth, tick_seconds=None))
    for user in ("maintainer", "reviewer1"):
        r = client.post("/api/register", headers=bearer(keycloak_token(user)),
                        json={"pseudonym": f"kc-{user}", "notice_acknowledged": True})
        assert r.status_code == 200, r.text
    boss, rev = bearer(keycloak_token("maintainer")), bearer(keycloak_token("reviewer1"))
    assert client.get("/api/me", headers=boss).json()["maintainer"] is True
    assert client.get("/api/me", headers=rev).json()["maintainer"] is False
    assert client.get("/api/admin/submissions", headers=boss).status_code == 200
    assert client.get("/api/admin/submissions", headers=rev).status_code == 403
