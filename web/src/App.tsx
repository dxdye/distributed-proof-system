import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type Me, type Session } from "./api";
import { loadAuth, signOut, type Provider } from "./auth";
import { DeclarationView } from "./views/Declaration";
import { BrandMark, SiteFooter } from "./components/Layout";
import { StorageNotice } from "./components/StorageNotice";
import { UserMenu } from "./components/UserMenu";
import { useRoute } from "./router";
import { Admin } from "./views/Admin";
import { Discussions, ThreadView } from "./views/Discussions";
import { History } from "./views/History";
import { LeaseView } from "./views/LeaseView";
import { ProgressDetailView, ProgressList } from "./views/Progress";
import { How } from "./views/How";
import { HowOrganisation, HowPlantedErrors, HowStatistics } from "./views/HowMore";
import { Imprint, Privacy } from "./views/Legal";
import { JoinForm, SignIn } from "./views/Register";
import { Work } from "./views/Work";

/** `routes`: extra pages of a special build (the click dummy's role choice). */
export function App({ routes }: { routes?: Record<string, JSX.Element> }) {
  const route = useRoute();
  const [providers, setProviders] = useState<Provider[] | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);
  // On phones the navigation folds into a menu; it closes on every page change.
  const [menuOpen, setMenuOpen] = useState(false);
  const where = route.join("/");
  useEffect(() => setMenuOpen(false), [where]);

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
  if (routes?.[page]) body = routes[page];
  else if (page === "how")
    body =
      route[1] === "organisation" ? (
        <HowOrganisation />
      ) : route[1] === "planted-errors" ? (
        <HowPlantedErrors />
      ) : route[1] === "statistics" ? (
        <HowStatistics />
      ) : (
        <How />
      );
  else if (page === "imprint") body = <Imprint />;
  else if (page === "privacy") body = <Privacy />;
  else if (error) body = <p className="error">{error}</p>;
  // Statistics became part of the progress page; old links still work.
  else if ((page === "progress" && !route[2]) || page === "stats")
    body = route[1] ? (
      <ProgressDetailView key={route[1]} sid={decodeURIComponent(route[1])} me={me} />
    ) : (
      <ProgressList me={me} />
    );
  else if (!providers || !session) body = <p className="muted">Loading…</p>;
  else if (!session.authenticated) body = <SignIn providers={providers} onSignedIn={refresh} />;
  else if (!session.registered) body = <JoinForm onDone={refresh} title="Choose your pseudonym" />;
  else if (!me) body = <p className="muted">Loading…</p>;
  else if (page === "lease" && route[1]) body = <LeaseView id={route[1]} reload={reload} />;
  else if (page === "history") body = <History me={me} />;
  else if (page === "progress" && route[1] && route[2])
    body = me.maintainer ? (
      <DeclarationView
        key={`${route[1]}/${route[2]}`}
        sid={decodeURIComponent(route[1])}
        decl={decodeURIComponent(route[2])}
      />
    ) : (
      <p className="muted">Only maintainers see declarations under review.</p>
    );
  else if (page === "discussions") body = <Discussions />;
  else if (page === "thread" && route[1] && route[2])
    body = (
      <ThreadView
        key={`${route[1]}/${route[2]}`}
        sid={decodeURIComponent(route[1])}
        decl={decodeURIComponent(route[2])}
      />
    );
  else if (page === "admin" && (me.admin || me.maintainer)) body = <Admin me={me} />;
  else body = <Work me={me} reload={reload} openPreferences={route[1] === "preferences"} />;

  const current = (name: string) => (page === name ? "page" : undefined);
  // Signed out: a way in from every page (the click dummy chooses a role instead).
  const signInNow = () => {
    if (import.meta.env.MODE === "demo") {
      window.location.hash = "#/choose-role";
      return;
    }
    window.location.hash = "#/work";
    setTimeout(
      () => document.getElementById("sign-in")?.scrollIntoView({ behavior: "smooth" }),
      80,
    );
  };
  return (
    <div className="app">
      <button className="skip" onClick={() => document.getElementById("main")?.focus()}>
        Skip to content
      </button>
      {/* Service bar and header stay at the top while scrolling. */}
      <div className="masthead">
        <div className="service-bar">
          <div className="container">
            <span>Research prototype · Review of Lean 4 formalizations</span>
            {session?.authenticated ? (
              <UserMenu
                me={me}
                onSignOut={async () => {
                  setMe(null);
                  setSession({ authenticated: false });
                  await signOut();
                }}
              />
            ) : (
              session && (
                <a
                  className="signin-link"
                  href={import.meta.env.MODE === "demo" ? "#/choose-role" : "#/work"}
                  onClick={(e) => {
                    e.preventDefault();
                    signInNow();
                  }}
                >
                  Sign in or join
                </a>
              )
            )}
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
            <button
              className="menu-toggle"
              aria-expanded={menuOpen}
              aria-controls="main-nav"
              aria-label="Menu"
              onClick={() => setMenuOpen(!menuOpen)}
            >
              <span className={menuOpen ? "menu-icon open" : "menu-icon"} aria-hidden="true" />
              <span className="menu-label">{menuOpen ? "Close" : "Menu"}</span>
            </button>
            <nav
              id="main-nav"
              className={menuOpen ? "main-nav open" : "main-nav"}
              aria-label="Main"
            >
              {/* Your work · public · your role */}
              {signedIn && (
                <>
                  <a href="#/work" aria-current={current("work") ?? current("lease")}>
                    Review
                  </a>
                  <a
                    href="#/discussions"
                    aria-current={current("discussions") ?? current("thread")}
                  >
                    Discussions
                  </a>
                  <span className="nav-sep" aria-hidden="true" />
                </>
              )}
              <a href="#/progress" aria-current={current("progress") ?? current("stats")}>
                Progress
              </a>
              <a href="#/how" aria-current={current("how")}>
                How it works
              </a>
              {(me?.admin || me?.maintainer) && (
                <>
                  <span className="nav-sep" aria-hidden="true" />
                  <a href="#/admin" aria-current={current("admin")}>
                    {me?.admin ? "Administration" : "Maintenance"}
                  </a>
                </>
              )}
              {session && !session.authenticated && (
                <>
                  <span className="nav-sep" aria-hidden="true" />
                  <button className="nav-cta" onClick={signInNow}>
                    Sign in or join
                  </button>
                </>
              )}
            </nav>
          </div>
        </header>
      </div>
      <main id="main" className="container" tabIndex={-1}>
        {body}
      </main>
      <SiteFooter />
      <StorageNotice />
    </div>
  );
}
