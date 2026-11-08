/-!
Fixture for the mutation generator and the local equivalence filter (SR-07).

Expected (see tests/test_mutation.py):
* `pos_le`: `0 < n` → `0 ≤ n` and `1 ≤ n` → `1 < n` change the meaning (kept);
  `0 < n` → `1 < n` is *true* but a different claim (kept — a whole-statement
  filter `M ↔ D` would wrongly discard it).
* `total`: `b < a` → `b ≤ a` leaves `a ≤ b ∨ b < a` equivalent at the place of
  the change only together with the other disjunct — locally `b < a ↔ b ≤ a`
  is false, so it is kept.
* `redundant`: hypothesis `h₂ : 0 < n` follows from `h₁ : 1 < n`; dropping it
  does not change the meaning (discarded).
* `exists_gt`: `∀ n, ∃ m, n < m` → `∃ m, ∀ n, n < m` (kept).
* `double`: body `2 * n` → `3 * n` / `1 * n` changes the definition (kept).
* `succ_pos'`: `0 < n + 1` → `0 ≤ n + 1` holds on both sides (discarded).
* `plusZero`: body `n + 0` → `n + 1` (kept).
-/

namespace Mut

theorem pos_le (n : Nat) (h : 0 < n) : 1 ≤ n := h

theorem total (a b : Nat) : a ≤ b ∨ b < a := by omega

theorem redundant (n : Nat) (h₁ : 1 < n) (h₂ : 0 < n) : 2 ≤ n := by omega

theorem exists_gt : ∀ n : Nat, ∃ m, n < m := fun n => ⟨n + 1, Nat.lt_succ_self n⟩

/-- `0 < n + 1` → `0 ≤ n + 1` is equivalent at the place of the change (both
always hold for natural numbers): must be discarded. -/
theorem succ_pos' (n : Nat) : 0 < n + 1 := Nat.succ_pos n

def double (n : Nat) : Nat := 2 * n

/-- A definition whose literal can be changed without changing its meaning:
`n + 0 = n`, so the mutant `n + 0` → … is checked against the original. -/
def plusZero (n : Nat) : Nat := n + 0

end Mut
