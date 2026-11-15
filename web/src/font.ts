// Text font: Inter by default; JetBrains Mono Nerd Font can be chosen for the
// current visit. Like the colour scheme, the choice is kept in session storage
// only (see the privacy policy), and index.html applies it before the first
// paint. Code is always set in JetBrains Mono.

export type FontChoice = "sans" | "mono";

const KEY = "dpc.font";

export function getFont(): FontChoice {
  return sessionStorage.getItem(KEY) === "mono" ? "mono" : "sans";
}

export function setFont(choice: FontChoice): void {
  if (choice === "sans") sessionStorage.removeItem(KEY);
  else sessionStorage.setItem(KEY, choice);
  applyFont(choice);
}

export function applyFont(choice: FontChoice = getFont()): void {
  const root = document.documentElement;
  if (choice === "sans") root.removeAttribute("data-font");
  else root.setAttribute("data-font", choice);
}
