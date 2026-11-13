// Colour scheme: follow the system, or light / dark as chosen. The choice is
// a display preference stored in this browser only (see the privacy policy).
// index.html applies it before the first paint, so the page does not flash.

export type ThemeChoice = "system" | "light" | "dark";

const KEY = "dpc.theme";

export function getTheme(): ThemeChoice {
  const v = localStorage.getItem(KEY);
  return v === "light" || v === "dark" ? v : "system";
}

export function setTheme(choice: ThemeChoice): void {
  if (choice === "system") localStorage.removeItem(KEY);
  else localStorage.setItem(KEY, choice);
  applyTheme(choice);
}

export function applyTheme(choice: ThemeChoice = getTheme()): void {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
}
