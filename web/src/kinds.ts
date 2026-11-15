// How declarations and domains are named on screen.

/** The three kinds the checklist distinguishes (dpc/tickets/questions.py,
 * kind_of): a theorem claims something, a definition fixes a word, a
 * structure bundles conditions. Lean's own kinds (def, opaque, inductive …)
 * mean little to a reviewer. */
export function kindLabel(declKind: string): "Theorem" | "Definition" | "Structure" {
  if (declKind === "theorem") return "Theorem";
  if (declKind === "inductive") return "Structure";
  return "Definition";
}

/** Domains are stored as keys such as number_theory. */
export const domainLabel = (domain: string): string => domain.replace(/_/g, " ");

/** A Lean name as namespace and short name: OAI.Seymour.GoodVertex gives
 * ("OAI.Seymour", "GoodVertex"). */
export function splitName(name: string): { ns: string; short: string } {
  const i = name.lastIndexOf(".");
  return i < 0 ? { ns: "", short: name } : { ns: name.slice(0, i), short: name.slice(i + 1) };
}
