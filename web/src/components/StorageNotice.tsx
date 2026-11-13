import { useState } from "react";

// Information notice, not a consent banner: the site stores only what signing
// in technically requires, which needs no consent (§ 25 (2) no. 2 TDDDG).
// Anything optional added later (analytics, embedded third-party content)
// would need real opt-in consent before it runs.

const KEY = "dpc.storage-notice";

export function StorageNotice() {
  const [seen, setSeen] = useState(() => localStorage.getItem(KEY) === "1");
  if (seen) return null;
  return (
    <div className="storage-notice" role="region" aria-label="Storage notice">
      <p>
        This site stores only what signing in needs: your session in this browser and the session
        cookies of the sign-in service. No tracking, no analytics.
        <br />
        <span lang="de">
          Diese Seite speichert nur, was die Anmeldung braucht: Ihre Sitzung in diesem Browser und
          die Sitzungs-Cookies des Anmeldedienstes. Kein Tracking, keine Analyse.
        </span>{" "}
        <a href="#/privacy">Privacy policy / Datenschutz</a>
      </p>
      <button
        onClick={() => {
          localStorage.setItem(KEY, "1");
          setSeen(true);
        }}
      >
        OK
      </button>
    </div>
  );
}
