/-!
Fixture with a hand-checked trusted computing base (SR-03, verification §11.2).

Expected for `Basic.main_theorem`:
* TCB units (new, i.e. outside core): `main_theorem`, `isEven`, `double`, `Point`,
  `instAddPoint`, `Color`, `Color.toNat`, `sumTo`, `secret`, `offset` (private).
* Only in the proof (class B): `helper`, `proofOnlyDef`.
* Not reachable at all: `unused`.
-/

namespace Basic

def double (n : Nat) : Nat := n + n

def isEven (n : Nat) : Prop := ∃ k, n = double k

structure Point where
  x : Nat
  y : Nat

instance instAddPoint : Add Point := ⟨fun a b => ⟨a.x + b.x, a.y + b.y⟩⟩

inductive Color where
  | red
  | green

def Color.toNat : Color → Nat
  | .red => 0
  | .green => 1

def sumTo : Nat → Nat
  | 0 => 0
  | n + 1 => (n + 1) + sumTo n

/-- Opaque: only its type belongs to the TCB, the kernel never unfolds the body. -/
opaque secret : Nat

private def offset : Nat := 0

def proofOnlyDef (n : Nat) : Nat := n * 1

theorem helper (n : Nat) : 2 * n = double (proofOnlyDef n) := by
  unfold double proofOnlyDef
  omega

/-- Main theorem of the fixture. -/
theorem main_theorem (p : Point) (c : Color) :
    isEven (2 * ((p + p).x + c.toNat + sumTo 0 + secret * 0 + offset)) :=
  ⟨_, helper _⟩

def unused : Nat := 42

/-! Roots with non-standard axioms (SR-02). -/

axiom bold_claim : ∀ n : Nat, n = n + 0

theorem uses_axiom : (5 : Nat) = 5 + 0 := bold_claim 5

theorem sorried : 1 = 2 := by sorry

theorem native_root : 2 + 2 = 4 := by native_decide

theorem standard_root : ∀ p : Prop, p ∨ ¬p := Classical.em

end Basic
