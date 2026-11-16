"""OpenID Connect providers: Keycloak, and any other OIDC issuer by configuration.

The web client signs in with the authorization code flow and PKCE and sends the
access token as bearer token. The API checks it locally:
- the signature, with the provider's published keys (JWKS);
- the issuer and the audience, so that only tokens minted for this API count;
- expiry, with a small leeway.

Only asymmetric algorithms are accepted, so a token signed with the public key
as an HMAC secret is rejected.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import httpx
import jwt

from dpc.auth.base import AuthError, Identity

#: Asymmetric signature algorithms only (no `none`, no HMAC).
ALGORITHMS = ("RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512")

KeyResolver = Callable[[str], Any]


def claim_path(claims: dict[str, Any], path: str) -> Any:
    """``realm_access.roles`` → ``claims["realm_access"]["roles"]`` (None if absent)."""
    node: Any = claims
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


class OidcProvider:
    kind = "oidc"

    def __init__(
        self, *, name: str, issuer: str, client_id: str, audience: str, label: str = "",
        roles_claim: str = "roles", admin_role: str | None = None,
        jwks_uri: str | None = None, scopes: str = "openid",
        algorithms: Sequence[str] = ALGORITHMS, leeway_s: int = 30,
        key_resolver: KeyResolver | None = None,
    ) -> None:
        self.name = name
        self.label = label or name
        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self.audience = audience
        self.roles_claim = roles_claim
        self.admin_role = admin_role
        self.scopes = scopes
        self.algorithms = [a for a in algorithms if a in ALGORITHMS]
        self.leeway_s = leeway_s
        self._jwks_uri = jwks_uri
        self._jwks: jwt.PyJWKClient | None = None
        self._key_resolver = key_resolver  # tests: a fixed key instead of fetching JWKS

    # ------------------------------------------------------------ provider
    def accepts(self, token: str) -> bool:
        try:
            claims = jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError:
            return False
        return isinstance(claims, dict) and str(claims.get("iss", "")).rstrip("/") == self.issuer

    def authenticate(self, token: str) -> Identity:
        key = self._signing_key(token)
        try:
            claims = jwt.decode(
                token, key=key, algorithms=self.algorithms, audience=self.audience,
                issuer=self.issuer, leeway=self.leeway_s,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthError(f"{self.name}: invalid token ({exc})") from exc
        admin = None
        if self.admin_role is not None:
            roles = claim_path(claims, self.roles_claim)
            admin = isinstance(roles, list) and self.admin_role in roles
        return Identity(self.name, str(claims["sub"]), admin)

    def public_config(self) -> dict[str, str]:
        return {"kind": self.kind, "name": self.name, "label": self.label,
                "issuer": self.issuer, "client_id": self.client_id, "scopes": self.scopes}

    # ---------------------------------------------------------------- keys
    def _signing_key(self, token: str) -> Any:
        if self._key_resolver is not None:
            return self._key_resolver(token)
        try:
            return self._jwks_client().get_signing_key_from_jwt(token).key
        except (jwt.PyJWKClientError, httpx.HTTPError) as exc:
            raise AuthError(f"{self.name}: signing keys unavailable ({exc})", 503) from exc
        except jwt.PyJWTError as exc:
            raise AuthError(f"{self.name}: invalid token ({exc})") from exc

    def _jwks_client(self) -> jwt.PyJWKClient:
        if self._jwks is None:
            uri = self._jwks_uri or self._discover()["jwks_uri"]
            self._jwks = jwt.PyJWKClient(uri, cache_keys=True, lifespan=300, timeout=10)
        return self._jwks

    def _discover(self) -> dict[str, Any]:
        url = f"{self.issuer}/.well-known/openid-configuration"
        doc: dict[str, Any] = httpx.get(url, timeout=10).raise_for_status().json()
        if str(doc.get("issuer", "")).rstrip("/") != self.issuer:
            raise AuthError(f"{self.name}: discovery document names another issuer", 503)
        return doc


def keycloak(
    *, url: str, realm: str, client_id: str, audience: str, name: str = "keycloak",
    label: str = "Keycloak", admin_role: str | None = "dpc-maintainer",
    internal_url: str | None = None, scopes: str = "openid",
    key_resolver: KeyResolver | None = None,
) -> OidcProvider:
    """A Keycloak realm. ``url`` is the address browsers use (it is part of the
    token's issuer); ``internal_url`` optionally the address this server uses
    to fetch the signing keys. Realm roles are in ``realm_access.roles``."""
    base = url.rstrip("/")
    jwks = None
    if internal_url:
        jwks = f"{internal_url.rstrip('/')}/realms/{realm}/protocol/openid-connect/certs"
    return OidcProvider(
        name=name, label=label, issuer=f"{base}/realms/{realm}", client_id=client_id,
        audience=audience, roles_claim="realm_access.roles", admin_role=admin_role,
        jwks_uri=jwks, scopes=scopes, key_resolver=key_resolver,
    )
