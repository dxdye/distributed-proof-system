// Difficulty tiers (dpc/coord/tiers.py): a coarse reading of the estimated
// difficulty. Shown on ticket cards and in the ticket header.

export const TIER_LABELS: Record<string, string> = {
  easy: "Easy",
  medium: "Medium",
  hard: "Hard",
  excellence: "Excellence",
};

export const TIER_HINTS: Record<string, string> = {
  easy: "Short declaration, few dependencies.",
  medium: "Typical declaration.",
  hard: "Many dependencies or deep in the formalization. Open with experience in the domain (PV), as a doctoral student or expert.",
  excellence: "The most demanding declarations. Open to proven re-checkers (PVV) and experts.",
};

export function TierBadge({ tier }: { tier?: string }) {
  if (!tier) return null;
  return (
    <span className={`badge tier tier-${tier}`} title={TIER_HINTS[tier]}>
      {TIER_LABELS[tier] ?? tier}
    </span>
  );
}
