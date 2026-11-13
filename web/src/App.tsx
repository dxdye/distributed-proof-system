import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type Me, type Session } from "./api";
import { loadAuth, signOut, type Provider } from "./auth";
import { BrandMark, SiteFooter } from "./components/Layout";
import { StorageNotice } from "./components/StorageNotice";
import { useRoute } from "./router";
import { Admin } from "./views/Admin";
import { History } from "./views/History";
import { LeaseView } from "./views/LeaseView";
import { How } from "./views/How";
import { Imprint, Privacy } from "./views/Legal";
import { JoinForm, SignIn } from "./views/Register";
import { StatsView } from "./views/StatsView";
import { Work } from "./views/Work";

export function App() {
  const route = useRoute();
  const [providers, setProviders] = useState<Provider[] | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Who is signed in, and does that sign-in have a reviewer account?
  const refresh = useCallback(async () => {
    try {
      const s = await api.session();
      setSession(s);
      setMe(s.authenticated && s.registered ? await api.me() : null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    loadAuth()
      .then(setProviders)
      .then(refresh)
      .catch((e) => setError((e as Error).message));
  }, [refresh]);

  const reload = useCallback(() => {
    api
      .me()
      .then(setMe)
      .catch((e) => {
        if (e instanceof ApiError && (e.status === 401 || e.status === 403)) refresh();
      });
  }, [refresh]);

  const signedIn = Boolean(session?.authenticated && session.registered);
  const page = route[0] ?? "work";
  let body;
  if (page === "how") body = <How />;
  else if (page === "imprint") body = <Imprint />;
  else if (page === "privacy") body = <Privacy />;
  else if (error) body = <p className="error">{error}</p>;
  else if (page === "stats") body = <StatsView />;
  else if (!providers || !session) body = <p className="muted">Loading…</p>;
  else if (!session.authenticated) body = <SignIn providers={providers} onSignedIn={refresh} />;
  else if (!session.registered) body = <JoinForm onDone={refresh} title="Choose your pseudonym" />;
  else if (!me) body = <p className="muted">Loading…</p>;
  else if (page === "lease" && route[1]) body = <LeaseView id={route[1]} reload={reload} />;
  else if (page === "history") body = <History me={me} />;
  else if (page === "admin" && me.maintainer) body = <Admin />;
  else body = <Work me={me} reload={reload} />;

  const current = (name: string) => (page === name ? "page" : undefined);
  return (
    <div className="app">
      <button className="skip" onClick={() => document.getElementById("main")?.focus()}>
        Skip to content
      </button>
      <div className="service-bar">
        <div className="container">
          <span>Research prototype · Review of Lean 4 formalizations</span>
        </div>
      </div>
      <header className="site-header">
        <div className="container header-inner">
          <a className="brand" href="#/work">
            <BrandMark />
            <span className="brand-text">
              <strong>Distributed Proof Check</strong>
              <small>Human review of machine-checked mathematics</small>
            </span>
          </a>
          <nav className="main-nav" aria-label="Main">
            {signedIn && (
              <a href="#/work" aria-current={current("work") ?? current("lease")}>
                Review
              </a>
            )}
            {signedIn && (
              <a href="#/history" aria-current={current("history")}>
                My reviews
              </a>
            )}
            <a href="#/how" aria-current={current("how")}>
              How it works
            </a>
            <a href="#/stats" aria-current={current("stats")}>
              Statistics
            </a>
            {me?.maintainer && (
              <a href="#/admin" aria-current={current("admin")}>
                Maintainers
              </a>
            )}
          </nav>
          {session?.authenticated && (
            <span className="who">
              {me && (
                <span>
                  Signed in as <strong>{me.pseudonym}</strong>
                </span>
              )}
              <button
                className="secondary small"
                onClick={async () => {
                  setMe(null);
                  setSession({ authenticated: false });
                  await signOut();
                }}
              >
                Sign out
              </button>
            </span>
          )}
        </div>
      </header>
      <main id="main" className="container" tabIndex={-1}>
        {body}
      </main>
      <SiteFooter />
      <StorageNotice />
    </div>
  );
}
