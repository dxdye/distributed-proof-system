/-! A submission that brings its own display rule (docs/adr/0011). -/

namespace Display

structure Point where
  x : Nat
  y : Nat

def Point.sum (p : Point) : Nat := p.x + p.y

def double (n : Nat) : Nat := 2 * n

theorem sum_comm (p : Point) : p.sum = p.y + p.x := by
  unfold Point.sum; omega

/-- Misleading display rule: every `a ≤ b` is shown as `a < b`. -/
@[app_unexpander LE.le] def showLeAsLt : Lean.PrettyPrinter.Unexpander
  | `($_ $a $b) => `($a < $b)
  | _ => throw ()

/-- Shown as `0 < n → n < n + 1` with the rule above: a different claim. -/
theorem claim (n : Nat) (h : 0 ≤ n) : n ≤ n + 1 := by omega

end Display
