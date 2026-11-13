"""The service's own API tokens: issued at registration, stored hashed in the vault.

Kept for development, demos and tests, and for deployments without an
identity provider. Can be switched off in the configuration.
"""

from __future__ import annotations

from dpc.auth.base import LOCAL, AuthError, Identity
from dpc.coord.vault import Vault


class LocalTokenProvider:
    name = LOCAL

    def __init__(self, vault: Vault) -> None:
        self.vault = vault

    def accepts(self, token: str) -> bool:
        return "." not in token  # tokens are URL-safe base64; JWTs contain dots

    def authenticate(self, token: str) -> Identity:
        rid = self.vault.reviewer_for_token(token)
        if rid is None:
            raise AuthError("unknown token")
        return Identity(LOCAL, rid)

    def public_config(self) -> dict[str, str]:
        return {"kind": "local", "name": LOCAL, "label": "Access token"}
