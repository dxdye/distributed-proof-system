import { useEffect, useState } from "react";
import { api, setToken } from "../api";

// Pseudonymous registration (SR-23) with the notice on the use of review data (SR-49).
export function Register({ onDone }: { onDone: () => void }) {
  const [notice, setNotice] = useState<{ version: string; text: string } | null>(null);
  const [pseudonym, setPseudonym] = useState("");
  const [group, setGroup] = useState("other");
  const [affiliations, setAffiliations] = useState("");
  const [ack, setAck] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [token, setNewToken] = useState<string | null>(null);
  const [existing, setExisting] = useState("");

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
      setNewToken(res.token);
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
            setToken(token);
            onDone();
          }}
        >
          I have stored it — continue
        </button>
      </div>
    );
  }

  return (
    <div className="columns">
      <div className="card narrow">
        <h2>Join as reviewer</h2>
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
          </div>
        )}
        {error && <p className="error">{error}</p>}
        <button disabled={!pseudonym || !ack} onClick={submit}>
          Register
        </button>
      </div>
      <div className="card narrow">
        <h2>Sign in</h2>
        <label>
          Access token
          <input value={existing} onChange={(e) => setExisting(e.target.value)} />
        </label>
        <button
          disabled={!existing}
          onClick={() => {
            setToken(existing.trim());
            onDone();
          }}
        >
          Sign in
        </button>
      </div>
    </div>
  );
}
