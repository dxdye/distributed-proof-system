import { useCallback, useEffect, useState } from "react";
import { api, ApiError, getToken, setToken, type Me } from "./api";
import { useRoute } from "./router";
import { Admin } from "./views/Admin";
import { History } from "./views/History";
import { LeaseView } from "./views/LeaseView";
import { Register } from "./views/Register";
import { StatsView } from "./views/StatsView";
import { Work } from "./views/Work";

export function App() {
  const route = useRoute();
  const [me, setMe] = useState<Me | null>(null);
  const [signedIn, setSignedIn] = useState(Boolean(getToken()));

  const reload = useCallback(() => {
    if (!getToken()) return;
    api
      .me()
      .then(setMe)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) {
          setToken(null);
          setSignedIn(false);
        }
      });
  }, []);
  useEffect(reload, [reload, signedIn]);

  const page = route[0] ?? "work";
  let body;
  if (page === "stats") body = <StatsView />;
  else if (!signedIn) body = <Register onDone={() => setSignedIn(true)} />;
  else if (!me) body = <p className="muted">Loading…</p>;
  else if (page === "lease" && route[1]) body = <LeaseView id={route[1]} reload={reload} />;
  else if (page === "history") body = <History me={me} />;
  else if (page === "admin" && me.maintainer) body = <Admin />;
  else body = <Work me={me} reload={reload} />;

  return (
    <div className="app">
      <header>
        <a className="brand" href="#/work">
          Distributed Proof Check
        </a>
        <nav>
          {signedIn && <a href="#/work">Work</a>}
          {signedIn && <a href="#/history">My reviews</a>}
          <a href="#/stats">Statistics</a>
          {me?.maintainer && <a href="#/admin">Maintainers</a>}
        </nav>
        {signedIn && (
          <span className="who">
            {me?.pseudonym}{" "}
            <button
              className="link"
              onClick={() => {
                setToken(null);
                setMe(null);
                setSignedIn(false);
              }}
            >
              sign out
            </button>
          </span>
        )}
      </header>
      <main>{body}</main>
    </div>
  );
}
