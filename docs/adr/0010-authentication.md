# ADR 0010 — Authentication: pluggable identity providers, Keycloak first

Status: accepted (2026-11-13) · implemented in `dpc/auth`, `dpc/api/app.py`,
`dpc/coord` (vault, maintainer events), `web/src/auth.ts`, `deploy/keycloak`

## Context

The specification fixes *what* accounts are, not *how* people sign in:
- **SR-23:** accounts are pseudonymous, and trust is published only in
  aggregate (GDPR).
- **SR-49:** registration discloses that review data is openly licensed and
  may be used for training.
- **SR-41 / C12:** external profiles (GitHub, ORCID, MathOverflow, …) are linked
  via OAuth, each at most once, and give a capped starting value for trust.
  This serves the trust model, not sign-in.
- **Concept §6:** PV and PVV are earned from trust in a domain. Maintainers are
  appointed. Who appoints them (OD-2) and who operates the system (OD-1) are
  open decisions.

The M4 MVP issued its own random API token at registration. There was no
password, no recovery and no second factor.

Who operates the system decides which login system is available. A university
chair brings its single sign-on, an association may run Keycloak. Keycloak is
supported now, and further systems must be addable later.

## Decision

**Provider interface.** An `AuthProvider` turns a bearer token into an
`Identity`: the provider name, a stable subject, and optionally whether the
provider grants the maintainer role. `Authenticator` hands a token to the first
provider that accepts it. Built in:
- **`local`:** the service's own API tokens. They are for development, demos,
  tests and deployments without an identity provider, and can be switched off.
- **`oidc`:** any OpenID Connect issuer. Adding one needs configuration only.
- **`keycloak`:** OIDC with Keycloak's conventions: the issuer
  `<url>/realms/<realm>` and realm roles in `realm_access.roles`.

How further login systems are added:
- *A university's single sign-on* usually speaks OIDC (configuration only), or
  SAML/Shibboleth. SAML is brokered by Keycloak (identity brokering), so it
  needs no code here either.
- *Anything else* gets a new `AuthProvider` and a config class in
  `dpc/auth/config.py`.

**Token check in the API.** The API checks:
- the signature, with the keys the provider publishes (JWKS, via OIDC
  discovery);
- the issuer;
- the audience `dpc-api`, so only tokens minted for this API count (Keycloak:
  audience mapper on the client);
- expiry, with 30 s leeway;
- the algorithm: asymmetric only. `none` and HMAC are refused, so the public key
  cannot double as a shared secret.

**Accounts stay pseudonymous.**
1. On the first sign-in the person chooses a pseudonym and acknowledges the
   notice (SR-49), as before.
2. The vault links `(provider, subject)` to the reviewer id `R-…`, with one
   reviewer per sign-in.
3. The audit log never sees the sign-in (SR-23).

The identity provider knows name and e-mail, and the vault holds the link
between the two. Both are personal data under the GDPR. Protecting them is the
operator's responsibility (OD-1).

**Rights.** Only the coarse role *maintainer* may come from the identity
provider (Keycloak realm role `dpc-maintainer`).
- Every grant and revocation becomes an event (`reviewer.maintainer_appointed` /
  `reviewer.maintainer_revoked`, `by: identity_provider`). The report can
  therefore still be derived from the log alone (SR-17).
- The provider only revokes what it granted. Appointments made by the operator
  on the command line stay.
- PV and PVV are never assigned from outside. They follow from trust in the log
  (concept §6).

**Web client.** It uses the authorization code flow with PKCE (`oidc-client-ts`).
The session lives in `sessionStorage` and is renewed silently with the refresh
token. Sign-out also ends the session at the provider. Local API tokens work as
before.

**Development setup.** `pixi run keycloak-up` starts Keycloak 26.4 in dev mode
with the realm from `deploy/keycloak/realm/dpc-realm.json`. The realm contains:
- the public client `dpc-web` (PKCE, audience mapper);
- the role `dpc-maintainer`;
- users `maintainer`, `reviewer1` and `reviewer2` (password = user name);
- the client `dpc-test` with password grant, for automated tests only.

`dpc serve --auth config/auth-keycloak.json` enables it. The login pages use
the theme `dpc` (`deploy/keycloak/themes`): keycloak.v2 with the colours, font and
mark of the web client, in light and dark mode. The dev users have fixed ids, so
re-importing the realm keeps their link to reviewer accounts.

## Consequences

- Sign-in, password reset, second factor and self-registration are Keycloak's
  job. The service only checks tokens.
- A role change in Keycloak takes effect with the next access token, i.e.
  within its lifetime (5 min in the dev realm).
- Tested against the real dev Keycloak:
  - password grant (`tests/test_auth.py`, marker `keycloak`);
  - the browser's code flow, scripted: PKCE enforced, CORS for the app's
    origin, refresh token, audience and role in the access token.
- Production needs more than the dev setup:
  - HTTPS;
  - Keycloak in production mode with its own database;
  - no `dpc-test` client and no dev users;
  - e-mail verification as the operator decides;
  - `local_tokens: false`.
- Tokens in `sessionStorage` can be read by injected script. A strict
  Content-Security-Policy is the counterpart. A backend-for-frontend with
  cookies would avoid this, at the cost of state on the server.

## Not covered

- **Linking external profiles for trust priors (SR-41, C12).** That means
  fetching scores per domain from GitHub, ORCID and others, and recording the
  capped prior as an event. It can use Keycloak's identity brokering for the
  OAuth part, but it is separate work.
- **Who appoints maintainers (OD-2).** Technically it is whoever administers
  the realm role. Organisationally it is open.
