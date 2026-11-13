// Sign-in (docs/adr/0010): the service's own API tokens, or OpenID Connect
// providers such as Keycloak (authorization code flow with PKCE). The server
// lists the configured methods at /api/auth/config.
import { UserManager, WebStorageStateStore } from "oidc-client-ts";

export type LocalProvider = { kind: "local"; name: string; label: string };
export type OidcProvider = {
  kind: "oidc";
  name: string;
  label: string;
  issuer: string;
  client_id: string;
  scopes: string;
};
export type Provider = LocalProvider | OidcProvider;

const TOKEN_KEY = "dpc.token"; // the service's own API token (localStorage)
const ACTIVE_KEY = "dpc.oidc-provider"; // OIDC provider signed in with (sessionStorage)

let providers: Provider[] = [];
const managers = new Map<string, UserManager>();

function managerFor(p: OidcProvider): UserManager {
  let m = managers.get(p.name);
  if (!m) {
    m = new UserManager({
      authority: p.issuer,
      client_id: p.client_id,
      redirect_uri: `${window.location.origin}/`,
      post_logout_redirect_uri: `${window.location.origin}/`,
      response_type: "code",
      scope: p.scopes,
      automaticSilentRenew: true,
      userStore: new WebStorageStateStore({ store: window.sessionStorage }),
    });
    managers.set(p.name, m);
  }
  return m;
}

function activeOidc(): OidcProvider | null {
  const name = sessionStorage.getItem(ACTIVE_KEY);
  const p = providers.find((x) => x.name === name);
  return p && p.kind === "oidc" ? p : null;
}

let loading: Promise<Provider[]> | null = null;

/** Loads the sign-in methods and completes a pending OIDC redirect (once). */
export function loadAuth(): Promise<Provider[]> {
  loading ??= (async () => {
    const res = await fetch("/api/auth/config");
    if (!res.ok) throw new Error(`sign-in configuration unavailable (${res.status})`);
    providers = (await res.json()).providers as Provider[];
    const params = new URLSearchParams(window.location.search);
    const active = activeOidc();
    if (active && params.has("code") && params.has("state")) {
      const user = await managerFor(active).signinRedirectCallback();
      const back = typeof user.state === "string" && user.state ? user.state : "#/work";
      window.history.replaceState(null, "", `${window.location.pathname}${back}`);
    }
    return providers;
  })();
  return loading;
}

export async function signInWith(p: OidcProvider): Promise<void> {
  localStorage.removeItem(TOKEN_KEY);
  sessionStorage.setItem(ACTIVE_KEY, p.name);
  await managerFor(p).signinRedirect({ state: window.location.hash || "#/work" });
}

export function signInWithToken(token: string): void {
  sessionStorage.removeItem(ACTIVE_KEY);
  localStorage.setItem(TOKEN_KEY, token.trim());
}

/** Bearer token for API calls: the OIDC access token or the local API token. */
export async function accessToken(): Promise<string | null> {
  const p = activeOidc();
  if (p) {
    const user = await managerFor(p).getUser();
    return user && !user.expired ? user.access_token : null;
  }
  return localStorage.getItem(TOKEN_KEY);
}

/** Signs out; for an identity provider also ends the session there. */
export async function signOut(): Promise<void> {
  const p = activeOidc();
  localStorage.removeItem(TOKEN_KEY);
  if (p) {
    sessionStorage.removeItem(ACTIVE_KEY);
    await managerFor(p).signoutRedirect();
  }
}
