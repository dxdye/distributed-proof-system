import Lean
import Replay.Honest

/-! A forged proof: the theorem `bogus` is added without the kernel ever
checking it. The build succeeds, and `main` depends on no axiom at all, so
the axiom check sees nothing. Only a kernel replay finds it. -/

open Lean Elab Command in
set_option debug.skipKernelTC true in
run_cmd liftCoreM <| addDecl <| .thmDecl {
  name := `Replay.bogus, levelParams := [], type := mkConst ``False,
  value := mkConst ``True.intro }

theorem Replay.main : False := Replay.bogus
