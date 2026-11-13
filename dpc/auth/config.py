"""Configuration of the sign-in methods (``dpc serve --auth FILE``).

Example (``config/auth-keycloak.json``)::

    {"local_tokens": true,
     "providers": [{"kind": "keycloak", "url": "http://localhost:8080", "realm": "dpc",
                    "client_id": "dpc-web", "audience": "dpc-api",
                    "maintainer_role": "dpc-maintainer"}]}

A new kind of provider gets a config class here and a branch in
:func:`build_authenticator`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from dpc.auth.base import Authenticator, AuthProvider
from dpc.auth.local import LocalTokenProvider
from dpc.auth.oidc import OidcProvider, keycloak
from dpc.coord.vault import Vault


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class KeycloakConfig(_Cfg):
    kind: Literal["keycloak"]
    name: str = "keycloak"
    label: str = "Keycloak"
    url: str  # as seen by browsers (part of the token issuer)
    internal_url: str | None = None  # as seen by this server, if different
    realm: str
    client_id: str
    audience: str
    maintainer_role: str | None = "dpc-maintainer"
    scopes: str = "openid"


class OidcConfig(_Cfg):
    kind: Literal["oidc"]
    name: str
    label: str = ""
    issuer: str
    client_id: str
    audience: str
    roles_claim: str = "roles"
    maintainer_role: str | None = None
    jwks_uri: str | None = None
    scopes: str = "openid"


ProviderConfig = Annotated[KeycloakConfig | OidcConfig, Field(discriminator="kind")]


class AuthConfig(_Cfg):
    #: The service's own API tokens (development, demos, deployments without an
    #: identity provider). Switch off in production with an identity provider.
    local_tokens: bool = True
    providers: tuple[ProviderConfig, ...] = ()


def load_auth_config(path: Path) -> AuthConfig:
    return AuthConfig.model_validate_json(path.read_text("utf-8"))


def build_authenticator(config: AuthConfig, vault: Vault) -> Authenticator:
    providers: list[AuthProvider] = []
    if config.local_tokens:
        providers.append(LocalTokenProvider(vault))
    for p in config.providers:
        if isinstance(p, KeycloakConfig):
            providers.append(keycloak(
                url=p.url, internal_url=p.internal_url, realm=p.realm, client_id=p.client_id,
                audience=p.audience, name=p.name, label=p.label,
                maintainer_role=p.maintainer_role, scopes=p.scopes))
        else:
            providers.append(OidcProvider(
                name=p.name, label=p.label, issuer=p.issuer, client_id=p.client_id,
                audience=p.audience, roles_claim=p.roles_claim,
                maintainer_role=p.maintainer_role, jwks_uri=p.jwks_uri, scopes=p.scopes))
    if not providers:
        raise ValueError("no sign-in method configured")
    return Authenticator(providers)
