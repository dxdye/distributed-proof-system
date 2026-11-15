import { useEffect, useState, type ReactNode } from "react";

// Imprint (§ 5 DDG) and privacy policy (Art. 13 GDPR). The operator's data
// comes from /legal.json at runtime, so a host can fill it in without a
// rebuild. Templates only: not legally reviewed. The German text is the
// authoritative one.

type LegalData = {
  operator: string;
  legal_form: string;
  represented_by: string;
  address: string[];
  email: string;
  phone: string;
  vat_id: string;
  supervisory_authority: string;
  content_responsible: string;
  dpo: string;
  dpa_authority: string;
  legal_basis: string;
  log_retention: string;
  account_retention: string;
  hosting: string;
};
type Lang = "de" | "en";

let loading: Promise<LegalData> | null = null;
function loadLegal(): Promise<LegalData> {
  loading ??= fetch(`${import.meta.env.BASE_URL}legal.json`).then((r) => {
    if (!r.ok) throw new Error(`legal.json unavailable (${r.status})`);
    return r.json() as Promise<LegalData>;
  });
  return loading;
}

/** Any value still a placeholder in [brackets]? */
function isDraft(d: LegalData): boolean {
  return Object.entries(d).some(([k, v]) => !k.startsWith("_") && JSON.stringify(v).includes("["));
}

function LegalPage({
  title,
  children,
}: {
  title: Record<Lang, string>;
  children: (d: LegalData, lang: Lang) => ReactNode;
}) {
  const [data, setData] = useState<LegalData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lang, setLang] = useState<Lang>("de");
  useEffect(() => {
    loadLegal()
      .then(setData)
      .catch((e) => setError((e as Error).message));
  }, []);
  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading…</p>;
  return (
    <div className="card legal">
      <div className="row">
        <h2>{title[lang]}</h2>
        <span className="lang">
          <button className="link" disabled={lang === "de"} onClick={() => setLang("de")}>
            Deutsch
          </button>
          {" | "}
          <button className="link" disabled={lang === "en"} onClick={() => setLang("en")}>
            English
          </button>
        </span>
      </div>
      {isDraft(data) && (
        <p className="draft">
          {lang === "de"
            ? "Entwurf: Angaben in [eckigen Klammern] sind Platzhalter. Der Text ist nicht rechtlich geprüft."
            : "Draft: values in [brackets] are placeholders. The text has not been legally reviewed."}
        </p>
      )}
      {lang === "en" && (
        <p className="small muted">
          Translation for convenience; the German version is authoritative.
        </p>
      )}
      {children(data, lang)}
    </div>
  );
}

function Address({ d }: { d: LegalData }) {
  return (
    <p>
      {d.operator}
      <br />
      {d.address.map((line) => (
        <span key={line}>
          {line}
          <br />
        </span>
      ))}
    </p>
  );
}

export function Imprint() {
  return (
    <LegalPage title={{ de: "Impressum", en: "Legal notice" }}>
      {(d, lang) =>
        lang === "de" ? (
          <>
            <h3>Angaben gemäß § 5 Digitale-Dienste-Gesetz (DDG)</h3>
            <Address d={d} />
            <p>
              {d.legal_form}
              <br />
              Vertreten durch: {d.represented_by}
            </p>
            <h3>Kontakt</h3>
            <p>
              E-Mail: {d.email}
              <br />
              Telefon: {d.phone}
            </p>
            <p>Umsatzsteuer-Identifikationsnummer: {d.vat_id}</p>
            <p>Zuständige Aufsichtsbehörde: {d.supervisory_authority}</p>
            <h3>Verantwortlich für den Inhalt nach § 18 Abs. 2 MStV</h3>
            <p>{d.content_responsible}</p>
            <h3>Datenschutz</h3>
            <p>
              Siehe <a href="#/privacy">Datenschutzerklärung</a>.
            </p>
          </>
        ) : (
          <>
            <h3>Information pursuant to § 5 of the German Digital Services Act (DDG)</h3>
            <Address d={d} />
            <p>
              {d.legal_form}
              <br />
              Represented by: {d.represented_by}
            </p>
            <h3>Contact</h3>
            <p>
              E-mail: {d.email}
              <br />
              Phone: {d.phone}
            </p>
            <p>VAT identification number: {d.vat_id}</p>
            <p>Supervisory authority: {d.supervisory_authority}</p>
            <h3>Responsible for the content (§ 18 (2) MStV)</h3>
            <p>{d.content_responsible}</p>
            <h3>Data protection</h3>
            <p>
              See the <a href="#/privacy">privacy policy</a>.
            </p>
          </>
        )
      }
    </LegalPage>
  );
}

export function Privacy() {
  return (
    <LegalPage title={{ de: "Datenschutzerklärung", en: "Privacy policy" }}>
      {(d, lang) => (lang === "de" ? <PrivacyDe d={d} /> : <PrivacyEn d={d} />)}
    </LegalPage>
  );
}

function PrivacyDe({ d }: { d: LegalData }) {
  return (
    <>
      <h3>1. Verantwortlicher</h3>
      <Address d={d} />
      <p>E-Mail: {d.email}</p>
      <p>Datenschutzbeauftragte bzw. Datenschutzbeauftragter: {d.dpo}</p>

      <h3>2. Worum es geht</h3>
      <p>
        Distributed Proof Check ist eine Plattform, auf der Freiwillige pseudonym prüfen, ob
        formalisierte mathematische Beweise (Lean 4) das aussagen, was die zugehörige Arbeit
        behauptet. Ihre Prüfungen werden mit den Berichten veröffentlicht, nur unter einer
        zufälligen Kennung.
      </p>

      <h3>3. Welche Daten wir verarbeiten</h3>
      <ul>
        <li>
          <b>Server-Protokolle:</b> IP-Adresse, Zeitpunkt, aufgerufene Adresse und Browserkennung,
          zur Sicherheit des Betriebs. Speicherdauer: {d.log_retention}.
        </li>
        <li>
          <b>Konto:</b> das selbst gewählte Pseudonym, die Gruppe (z. B. Studium, Promotion), die
          Version des bei der Registrierung bestätigten Hinweises und freiwillig angegebene
          Beschäftigungen oder Aufträge bei Laboren. Letztere stehen im Prüfprotokoll nur als
          Schlüssel-Hash (HMAC), damit Interessenkonflikte geprüft werden können, ohne sie
          offenzulegen.
        </li>
        <li>
          <b>Anmeldung:</b> Bei der Anmeldung über den Anmeldedienst (Keycloak) verarbeitet dieser
          Benutzernamen, E-Mail-Adresse, Namen und ein Passwort-Hash. Die Plattform speichert nur
          die Verknüpfung zwischen der Kennung des Anmeldedienstes und Ihrer zufälligen
          Prüfer-Kennung, getrennt vom Prüfprotokoll und nie veröffentlicht. Alternativ erhalten Sie
          ein Zugangs-Token, von dem nur ein Hash gespeichert wird.
        </li>
        <li>
          <b>Prüfungen:</b> Urteile, Begründungen, Belegdateien, Bearbeitungszeit und Ihre Angabe
          zur Nutzung von KI-Werkzeugen. Sie werden mit den Berichten unter einer offenen Lizenz
          veröffentlicht, nur mit Ihrer zufälligen Kennung, und können zum Training und zur
          Bewertung von KI-Systemen verwendet werden. Darauf weist die Registrierung hin.
        </li>
        <li>
          <b>Vertrauenswerte:</b> Aus Ihren Prüfungen berechnete Kennzahlen bestimmen, welche
          Aufgaben Sie übernehmen können. Veröffentlicht werden sie nur zusammengefasst, nie pro
          Person.
        </li>
        <li>
          <b>Prüfprotokoll:</b> Alle Vorgänge werden in einem fälschungssicheren, nur erweiterbaren
          Protokoll festgehalten. Es enthält keine Namen, Pseudonyme oder Anmeldedaten, nur
          zufällige Kennungen und Schlüssel-Hashes, und wird mit dem Bericht veröffentlicht.
        </li>
      </ul>

      <h3>4. Speicherung in Ihrem Browser</h3>
      <p>
        Gespeichert wird nur, was für die Anmeldung technisch erforderlich ist: Ihre Anmeldesitzung
        (Session Storage) bzw. Ihr Zugangs-Token, die Information, dass Sie den Speicherhinweis
        gelesen haben (Local Storage), ein für den aktuellen Besuch gewähltes Farbschema (Session
        Storage) sowie die Sitzungs-Cookies des Anmeldedienstes. Die Schriften werden von diesem
        Server geladen, nicht von Dritten. Dafür ist keine Einwilligung erforderlich (§ 25 Abs. 2
        Nr. 2 TDDDG). Es gibt keine Analyse- oder Tracking-Dienste und keine Inhalte Dritter.
      </p>

      <h3>5. Rechtsgrundlagen</h3>
      <p>{d.legal_basis}</p>

      <h3>6. Speicherdauer und Löschung</h3>
      <p>
        Konten: {d.account_retention}. Das Prüfprotokoll ist absichtlich unveränderlich. Bei einer
        Löschung wird die Verknüpfung zwischen Ihrem Konto und Ihrer zufälligen Kennung gelöscht;
        Ihre bereits veröffentlichten Prüfungen sind danach keiner Person mehr zuzuordnen.
      </p>

      <h3>7. Hosting</h3>
      <p>{d.hosting}</p>

      <h3>8. Ihre Rechte</h3>
      <p>
        Sie haben das Recht auf Auskunft, Berichtigung, Löschung, Einschränkung der Verarbeitung,
        Datenübertragbarkeit und Widerspruch sowie das Recht, eine Einwilligung jederzeit für die
        Zukunft zu widerrufen. Sie können sich bei einer Datenschutz-Aufsichtsbehörde beschweren:{" "}
        {d.dpa_authority}.
      </p>
    </>
  );
}

function PrivacyEn({ d }: { d: LegalData }) {
  return (
    <>
      <h3>1. Controller</h3>
      <Address d={d} />
      <p>E-mail: {d.email}</p>
      <p>Data protection officer: {d.dpo}</p>

      <h3>2. What this is about</h3>
      <p>
        Distributed Proof Check is a platform on which volunteers check, under a pseudonym, whether
        formalized mathematical proofs (Lean 4) state what the corresponding paper claims. Your
        reviews are published with the reports, under a random id only.
      </p>

      <h3>3. Data we process</h3>
      <ul>
        <li>
          <b>Server logs:</b> IP address, time, requested address and browser identification, for
          operational security. Retention: {d.log_retention}.
        </li>
        <li>
          <b>Account:</b> the pseudonym you chose, your group (e.g. student, doctoral), the version
          of the notice you acknowledged at registration, and any employment or commissions by labs
          you declare. The latter appear in the audit log only as a keyed hash (HMAC), so that
          conflicts of interest can be checked without disclosing them.
        </li>
        <li>
          <b>Sign-in:</b> When you sign in through the sign-in service (Keycloak), that service
          processes your user name, e-mail address, name and a password hash. The platform stores
          only the link between the sign-in service's id and your random reviewer id, separately
          from the audit log and never published. Alternatively you receive an access token, of
          which only a hash is stored.
        </li>
        <li>
          <b>Reviews:</b> verdicts, justifications, evidence files, processing time and your
          statement on the use of AI tools. They are published with the reports under an open
          licence, with your random id only, and may be used to train and evaluate AI systems.
          Registration points this out.
        </li>
        <li>
          <b>Trust values:</b> figures computed from your reviews decide which tasks you can take
          on. They are published only in aggregate, never per person.
        </li>
        <li>
          <b>Audit log:</b> every event is recorded in a tamper-evident, append-only log. It
          contains no names, pseudonyms or sign-in data, only random ids and keyed hashes, and is
          published with the report.
        </li>
      </ul>

      <h3>4. Storage in your browser</h3>
      <p>
        Only what signing in technically requires is stored: your sign-in session (session storage)
        or your access token, the fact that you have read the storage notice (local storage), a
        colour scheme and font chosen for the current visit (session storage), and the session
        cookies of the sign-in service. Fonts are served by this server, not by third parties. No
        consent is required for this (§ 25 (2) no. 2 TDDDG). There are no analytics or tracking
        services and no third-party content.
      </p>

      <h3>5. Legal basis</h3>
      <p>{d.legal_basis}</p>

      <h3>6. Retention and erasure</h3>
      <p>
        Accounts: {d.account_retention}. The audit log is deliberately immutable. On erasure, the
        link between your account and your random id is deleted; your published reviews can then no
        longer be attributed to a person.
      </p>

      <h3>7. Hosting</h3>
      <p>{d.hosting}</p>

      <h3>8. Your rights</h3>
      <p>
        You have the right of access, rectification, erasure, restriction of processing, data
        portability and objection, and the right to withdraw consent at any time with effect for the
        future. You may lodge a complaint with a data protection supervisory authority:{" "}
        {d.dpa_authority}.
      </p>
    </>
  );
}
