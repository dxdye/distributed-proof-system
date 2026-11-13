module

/-! A file of the module system: its private part must be replayed too. -/

namespace Replay.Modular

public def double (n : Nat) : Nat := 2 * n

private def secret : Nat := 21

private theorem double_secret : double secret = 42 := by decide

public theorem double_two : double 2 = 4 := by decide

end Replay.Modular
