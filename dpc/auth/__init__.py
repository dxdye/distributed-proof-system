"""Authentication: pluggable identity providers (docs/adr/0010)."""

from dpc.auth.base import LOCAL, Authenticator, AuthError, AuthProvider, Identity
from dpc.auth.config import AuthConfig, build_authenticator, load_auth_config
from dpc.auth.local import LocalTokenProvider
from dpc.auth.oidc import OidcProvider, keycloak

__all__ = [
    "LOCAL",
    "AuthConfig",
    "AuthError",
    "AuthProvider",
    "Authenticator",
    "Identity",
    "LocalTokenProvider",
    "OidcProvider",
    "build_authenticator",
    "keycloak",
    "load_auth_config",
]
