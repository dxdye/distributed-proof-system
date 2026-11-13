// Colour scheme: every visit starts with "Auto", i.e. the system setting.
// Light or dark can be chosen for the current visit; the choice is kept in
// session storage only (see the privacy policy). index.html applies it before
// the first paint, so the page does not flash.

export type ThemeChoice = "system" | "light" | "dark";

const KEY = "dpc.theme";

export function getTheme(): ThemeChoice {
  const v = sessionStorage.getItem(KEY);
  return v === "light" || v === "dark" ? v : "system";
}

export function setTheme(choice: ThemeChoice): void {
  if (choice === "system") sessionStorage.removeItem(KEY);
  else sessionStorage.setItem(KEY, choice);
  applyTheme(choice);
}

export function applyTheme(choice: ThemeChoice = getTheme()): void {
  // Earlier versions kept the choice across visits; start from "Auto" again.
  localStorage.removeItem(KEY);
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
}
