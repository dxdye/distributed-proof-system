/-! Ordinary declarations of every kind the kernel replays: they must pass. -/

namespace Replay

inductive Tree where
  | leaf : Tree
  | node : Tree → Tree → Tree

def Tree.size : Tree → Nat
  | .leaf => 1
  | .node l r => l.size + r.size + 1

structure Point where
  x : Nat
  y : Nat

theorem size_pos (t : Tree) : 0 < t.size := by
  cases t <;> simp [Tree.size]

/-- Partial and unsafe definitions are skipped by the replay (safe code cannot use them). -/
partial def loop (n : Nat) : Nat := if n = 0 then 0 else loop (n - 1)

unsafe def peek (n : Nat) : Nat := n

end Replay
