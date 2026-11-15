// Text font: Inter by default; JetBrains Mono Nerd Font can be chosen for the
// current visit, and so can fonts placed locally in public/local-fonts (never
// committed; see its README). Like the colour scheme, the choice is kept in
// session storage only (see the privacy policy). index.html applies the two
// built-in choices before the first paint. Code is always set in JetBrains Mono.

/** "sans" (Inter), "mono" (JetBrains Mono Nerd Font) or "local:<name>". */
export type FontChoice = string;

const KEY = "dpc.font";
const LOCAL = "local:";
/** Behind every local font: if its file is missing or broken, Inter shows. */
const FALLBACK =
  '"Inter Variable", Inter, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

export type LocalFont = {
  name: string;
  files?: { src: string; weight?: string; style?: string }[];
};

export function getFont(): FontChoice {
  return sessionStorage.getItem(KEY) ?? "sans";
}

export function setFont(choice: FontChoice): void {
  if (choice === "sans") sessionStorage.removeItem(KEY);
  else sessionStorage.setItem(KEY, choice);
  applyFont(choice);
}

/** A family name safe to put into a CSS value. */
const family = (name: string) => `"${name.replace(/["\\;{}<>]/g, "")}"`;

export function applyFont(choice: FontChoice = getFont()): void {
  const root = document.documentElement;
  root.style.removeProperty("--font-text");
  root.removeAttribute("data-font");
  if (choice === "mono") root.setAttribute("data-font", "mono");
  else if (choice.startsWith(LOCAL))
    root.style.setProperty("--font-text", `${family(choice.slice(LOCAL.length))}, ${FALLBACK}`);
}

export const localChoice = (name: string): FontChoice => LOCAL + name;

let loaded: Promise<LocalFont[]> | null = null;

/** The fonts listed in public/local-fonts/fonts.json, registered with the
 * browser; none if the file does not exist. A stored choice of a font that is
 * no longer listed falls back to Inter. */
export function localFonts(): Promise<LocalFont[]> {
  loaded ??= (async () => {
    const base = `${import.meta.env.BASE_URL}local-fonts/`;
    let fonts: LocalFont[] = [];
    try {
      const res = await fetch(`${base}fonts.json`, { cache: "no-cache" });
      const data: unknown = res.ok ? await res.json() : [];
      fonts = Array.isArray(data)
        ? data.filter((f): f is LocalFont => typeof f?.name === "string" && f.name.trim() !== "")
        : [];
    } catch {
      fonts = []; // no list, or not JSON (the dev server answers unknown paths with HTML)
    }
    for (const f of fonts) {
      for (const file of f.files ?? []) {
        try {
          const face = new FontFace(f.name, `url("${base}${encodeURI(file.src)}")`, {
            weight: file.weight ?? "400",
            style: file.style ?? "normal",
            display: "swap",
          });
          document.fonts.add(face);
        } catch {
          /* a broken entry: the text falls back to Inter */
        }
      }
    }
    const current = getFont();
    if (current.startsWith(LOCAL) && !fonts.some((f) => localChoice(f.name) === current))
      setFont("sans");
    return fonts;
  })();
  return loaded;
}
