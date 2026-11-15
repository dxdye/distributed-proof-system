import { useEffect, useState } from "react";
import { api } from "../api";
import { signInWith, signInWithToken, type OidcProvider, type Provider } from "../auth";
import { Intro } from "../components/Intro";
import { domainLabel } from "../kinds";

// Sign-in with an identity provider or an API token (docs/adr/0010), and the
// pseudonymous registration (SR-23) with the notice on review data (SR-49).

export function SignIn({
  providers,
  onSignedIn,
}: {
  providers: Provider[];
  onSignedIn: () => void;
}) {
  const oidc = providers.filter((p): p is OidcProvider => p.kind === "oidc");
  const local = providers.some((p) => p.kind === "local");
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  // The click dummy has no sign-in: you choose a role instead.
  const demo = import.meta.env.MODE === "demo";

  return (
    <>
      <section className="hero">
        <span className="eyebrow">Research prototype</span>
        <h1>Check that formal proofs say what the paper claims.</h1>
        <p className="lead">
          The Lean kernel checks that a proof is valid. It does not check that the statement means
          what the paper says. Distributed Proof Check closes that gap with careful human review,
          and measures how reliable that review is.
        </p>
        <div className="hero-actions">
          <button
            onClick={() =>
              demo
                ? (window.location.hash = "#/choose-role")
                : document.getElementById("sign-in")?.scrollIntoView({ behavior: "smooth" })
            }
          >
            Sign in or join
          </button>
          <a href="#/how">How it works</a>
        </div>
      </section>
      <Intro />
      <ol className="steps">
        <li>
          <strong>Machine checks</strong>
          <p>
            Every declaration of a submission passes the Lean kernel again; only the standard axioms
            are allowed.
          </p>
        </li>
        <li>
          <strong>Human review</strong>
          <p>
            Reviewers check, under a pseudonym, that statements and definitions mean what the paper
            claims.
          </p>
        </li>
        <li>
          <strong>Measured reliability</strong>
          <p>
            Planted errors and re-checks measure how well the review works. Reports are published
            openly.
          </p>
        </li>
      </ol>
      <div id="sign-in" />
      {demo ? (
        <section className="card">
          <h2>Sign in</h2>
          <p className="muted">
            This click dummy has no sign-in. Choose the role you want to see the platform from.
          </p>
          <button onClick={() => (window.location.hash = "#/choose-role")}>Choose your role</button>
        </section>
      ) : oidc.length > 0 ? (
        <>
          <div className="columns">
            <div className="card">
              <h2>Sign in</h2>
              <p className="muted">
                New here? After signing in you choose a pseudonym. Your sign-in stays private: the
                published audit log knows you only by a random id.
              </p>
              {oidc.map((p) => (
                <button
                  key={p.name}
                  onClick={() => signInWith(p).catch((e) => setError((e as Error).message))}
                >
                  Sign in with {p.label}
                </button>
              ))}
              {error && <p className="error">{error}</p>}
            </div>
            <div className="card">
              <h2>What you do here</h2>
              <ul className="checklist">
                <li>Take a ticket: one statement or definition of a formalization.</li>
                <li>Compare it with the paper and answer five short questions.</li>
                <li>Say whether it is correct, with a reason if it is not.</li>
              </ul>
              <p className="muted small">There is no countdown: take the time a ticket needs.</p>
            </div>
          </div>
          {local && (
            <details className="alt-access">
              <summary>Other ways to sign in: access token</summary>
              <TokenAccess onSignedIn={onSignedIn} token={token} setToken={setToken} />
            </details>
          )}
        </>
      ) : (
        local && <TokenAccess onSignedIn={onSignedIn} token={token} setToken={setToken} />
      )}
    </>
  );
}

/** Sign-in with the service's own API tokens (no identity provider). */
function TokenAccess({
  onSignedIn,
  token,
  setToken,
}: {
  onSignedIn: () => void;
  token: string;
  setToken: (t: string) => void;
}) {
  return (
    <div className="columns">
      <JoinForm onDone={onSignedIn} title="Join with an access token" />
      <div className="card">
        <h2>Sign in with an access token</h2>
        <label>
          Access token
          <input value={token} onChange={(e) => setToken(e.target.value)} />
        </label>
        <button
          disabled={!token}
          onClick={() => {
            signInWithToken(token);
            onSignedIn();
          }}
        >
          Sign in
        </button>
      </div>
    </div>
  );
}

/** Registration. Signed in with an identity provider, the account is linked to
 * that sign-in; otherwise the server issues an API token, shown once. */
export function JoinForm({
  onDone,
  title = "Join as reviewer",
}: {
  onDone: () => void;
  title?: string;
}) {
  const [notice, setNotice] = useState<{ version: string; text: string } | null>(null);
  const [pseudonym, setPseudonym] = useState("");
  const [group, setGroup] = useState("other");
  const [affiliations, setAffiliations] = useState("");
  const [ack, setAck] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [token, setNewToken] = useState<string | null>(null);
  const [known, setKnown] = useState<string[]>([]);
  const [domains, setDomains] = useState<string[]>([]);

  useEffect(() => {
    api
      .notice()
      .then(setNotice)
      .catch((e) => setError(String(e.message)));
    api
      .domains()
      .then(setKnown)
      .catch(() => {});
  }, []);

  async function submit() {
    setError(null);
    try {
      const res = await api.register({
        pseudonym,
        group,
        affiliations: affiliations
          .split(",")
          .map((a) => a.trim())
          .filter(Boolean),
        notice_acknowledged: ack,
        domains,
      });
      if (res.token) setNewToken(res.token);
      else onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (token) {
    return (
      <div className="card narrow">
        <h2>Your access token</h2>
        <p>
          This token is shown <b>once</b>. Keep it somewhere safe; it is your only way to sign in.
        </p>
        <pre className="term">{token}</pre>
        <button
          onClick={() => {
            signInWithToken(token);
            onDone();
          }}
        >
          I have stored it — continue
        </button>
      </div>
    );
  }

  return (
    <div className="card narrow">
      <h2>{title}</h2>
      <label>
        Pseudonym
        <input value={pseudonym} onChange={(e) => setPseudonym(e.target.value)} />
      </label>
      <label>
        Group
        <select value={group} onChange={(e) => setGroup(e.target.value)}>
          <option value="expert">Expert (PhD and beyond)</option>
          <option value="doctoral">Doctoral student</option>
          <option value="student">Student</option>
          <option value="other">Other</option>
        </select>
      </label>
      <label>
        Employment or commissions by labs (comma separated, optional)
        <input value={affiliations} onChange={(e) => setAffiliations(e.target.value)} />
      </label>
      {known.length > 0 && (
        <fieldset className="join-prefs">
          <legend>What would you like to work on? (optional)</legend>
          <div className="chip-row">
            {known.map((d) => (
              <button
                key={d}
                type="button"
                className="chip"
                aria-pressed={domains.includes(d)}
                onClick={() =>
                  setDomains(domains.includes(d) ? domains.filter((x) => x !== d) : [...domains, d])
                }
              >
                {domainLabel(d)}
              </button>
            ))}
          </div>
          <p className="muted small">
            A preference is not a qualification. It only raises the chance that such tickets are
            offered; the rest stays random. Trust comes from the work itself, and harder tickets
            open with experience. Nothing selected means: anything. You can change it later.
          </p>
        </fieldset>
      )}
      {notice && (
        <div className="notice">
          <p className="small">{notice.text}</p>
          <label className="inline">
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />I have
            read this notice ({notice.version}).
          </label>
          <p className="small">
            Details: <a href="#/privacy">privacy policy</a>.
          </p>
        </div>
      )}
      {error && <p className="error">{error}</p>}
      <button disabled={!pseudonym || !ack} onClick={submit}>
        Register
      </button>
    </div>
  );
}
