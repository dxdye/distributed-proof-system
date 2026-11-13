import { useEffect, useState } from "react";
import { api } from "../api";
import { signInWith, signInWithToken, type OidcProvider, type Provider } from "../auth";

// Sign-in with an identity provider or an API token (docs/adr/0010), and the
// pseudonymous registration (SR-23) with the notice on review data (SR-49).

export function SignIn({ providers, onSignedIn }: { providers: Provider[]; onSignedIn: () => void }) {
  const oidc = providers.filter((p): p is OidcProvider => p.kind === "oidc");
  const local = providers.some((p) => p.kind === "local");
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="columns">
      {oidc.length > 0 && (
        <div className="card narrow">
          <h2>Sign in</h2>
          <p className="small muted">
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
      )}
      {local && (
        <>
          <JoinForm onDone={onSignedIn} title={oidc.length ? "Or join with an access token" : "Join as reviewer"} />
          <div className="card narrow">
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
        </>
      )}
    </div>
  );
}

/** Registration. Signed in with an identity provider, the account is linked to
 * that sign-in; otherwise the server issues an API token, shown once. */
export function JoinForm({ onDone, title = "Join as reviewer" }: { onDone: () => void; title?: string }) {
  const [notice, setNotice] = useState<{ version: string; text: string } | null>(null);
  const [pseudonym, setPseudonym] = useState("");
  const [group, setGroup] = useState("other");
  const [affiliations, setAffiliations] = useState("");
  const [ack, setAck] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [token, setNewToken] = useState<string | null>(null);

  useEffect(() => {
    api.notice().then(setNotice).catch((e) => setError(String(e.message)));
  }, []);

  async function submit() {
    setError(null);
    try {
      const res = await api.register({
        pseudonym,
        group,
        affiliations: affiliations.split(",").map((a) => a.trim()).filter(Boolean),
        notice_acknowledged: ack,
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
      {notice && (
        <div className="notice">
          <p className="small">{notice.text}</p>
          <label className="inline">
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
            I have read this notice ({notice.version}).
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
