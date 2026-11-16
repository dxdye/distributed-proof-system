"""Who is calling: identities, providers, and the authenticator (docs/adr/0010).

An *identity provider* turns a credential (a bearer token) into an
:class:`Identity`: the provider's name, a stable subject id, and optionally
whether the provider grants the coarse role *administrator* (C-42; formerly
*maintainer*). Everything else a
person may do (PV, PVV, exclusion rules) is derived from the audit log, never
from the provider (concept §6, SR-17).

Adding a further login system (a university's single sign-on, another OIDC
provider, SAML through a broker) means implementing :class:`AuthProvider` and
registering it in :mod:`dpc.auth.config`. Generic OIDC providers need no code,
only configuration.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class AuthError(Exception):
    """The credential was missing, invalid, or could not be checked."""

    def __init__(self, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Identity:
    provider: str  # name of the configured provider, e.g. "keycloak" or "local"
    subject: str  # stable id within that provider (OIDC `sub`; reviewer id for local tokens)
    #: Whether the provider grants the administrator role (C-42). ``None``: the
    #: provider does not manage roles; administrators are appointed by the
    #: operator only. Maintainers of domains are appointed in the platform.
    admin: bool | None = None

    @property
    def local(self) -> bool:
        return self.provider == LOCAL


#: Name of the built-in provider for the service's own API tokens.
LOCAL = "local"


class AuthProvider(Protocol):
    @property
    def name(self) -> str: ...

    def accepts(self, token: str) -> bool:
        """Cheap check whether the credential is meant for this provider."""
        ...

    def authenticate(self, token: str) -> Identity:
        """Verify the credential; raises :class:`AuthError`."""
        ...

    def public_config(self) -> dict[str, str]:
        """What the web client needs to offer this sign-in method."""
        ...


class Authenticator:
    """All configured providers; a credential goes to the first that accepts it."""

    def __init__(self, providers: Sequence[AuthProvider]) -> None:
        names = [p.name for p in providers]
        if len(set(names)) != len(names):
            raise ValueError(f"provider names must be unique: {names}")
        self.providers = tuple(providers)

    @property
    def local_tokens(self) -> bool:
        return any(p.name == LOCAL for p in self.providers)

    def identify(self, token: str) -> Identity:
        for provider in self.providers:
            if provider.accepts(token):
                return provider.authenticate(token)
        raise AuthError("credential not accepted by any configured sign-in method")

    def public_config(self) -> dict[str, object]:
        return {"providers": [p.public_config() for p in self.providers]}
