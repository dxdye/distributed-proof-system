/-!
Fixture for the evidence check (SR-10, tests/test_evidence.py).

* `vacuous`: the hypotheses `3 ≤ n` and `n < 2` contradict each other, so the
  theorem says nothing; a vacuity proof confirms a claim by machine.
* `honest`: satisfiable hypotheses; no vacuity proof exists.
-/

namespace Claims

theorem vacuous (n : Nat) (h₁ : 3 ≤ n) (h₂ : n < 2) : n = 7 := by omega

theorem honest (n : Nat) (h : 1 ≤ n) : 0 < n := h

end Claims
