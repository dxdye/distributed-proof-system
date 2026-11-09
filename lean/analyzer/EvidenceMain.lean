import DpcAnalyzer
import DpcAnalyzer.Mutate

/-!
`dpc-evidence`: checks a Lean evidence file against the fixed commit (SR-10).

The evidence file has been compiled beforehand (module `DpcEvidence`, by the
plain `lean` binary in the same sandbox). This program then

1. imports it **without** running any initializer (no foreign code runs here),
2. replays every declaration of the evidence module through the kernel,
   starting from an environment that contains only the evidence's imports —
   so `set_option debug.skipKernelTC`, `addDecl` from meta code or a forged
   `.olean` cannot smuggle in an unchecked proof,
3. requires the theorem `dpc_evidence` and checks that it depends on the
   standard axioms only (own walk, not `collectAxioms`; `sorryAx` is not
   standard),
4. for `vacuity`, checks that `dpc_evidence` proves exactly the vacuity goal of
   the target declaration: `∀ xs, False` over the target's binders. Only then
   does the evidence *confirm* the claim by machine; other kinds are checked
   for validity, and a PVV judges their relevance.

Output: one JSON object.
-/

open Lean Meta DpcAnalyzer DpcAnalyzer.Mutate

def evidenceModule : Name := `DpcEvidence
def evidenceTheorem : Name := `dpc_evidence
def standardAxioms : Array Name := #[``propext, ``Classical.choice, ``Quot.sound]

structure Args where
  target : Name := .anonymous
  kind : String := ""
  out : Option System.FilePath := none

def parseArgs : List String → Args → Except String Args
  | [], a => .ok a
  | "--target" :: v :: rest, a => parseArgs rest { a with target := v.toName }
  | "--kind" :: v :: rest, a => parseArgs rest { a with kind := v }
  | "--out" :: v :: rest, a => parseArgs rest { a with out := some v }
  | x :: _, _ => .error s!"unexpected argument '{x}'"

/-- The declaration to hand to the kernel again. Evidence may contain theorems
and (safe) definitions only: no axioms, no new inductive types, nothing unsafe. -/
def toDeclaration (n : Name) : ConstantInfo → Except String Declaration
  | .thmInfo v => .ok (.thmDecl v)
  | .defnInfo v =>
    if v.safety != .safe then .error s!"{n}: unsafe or partial definitions are not allowed"
    else .ok (.defnDecl v)
  | .opaqueInfo v =>
    if v.isUnsafe then .error s!"{n}: unsafe constants are not allowed" else .ok (.opaqueDecl v)
  | .axiomInfo _ => .error s!"{n}: evidence must not declare axioms"
  | _ => .error s!"{n}: evidence may contain theorems and definitions only"

/-- Replay `n` and, first, the evidence constants it uses. -/
partial def replay (src : Environment) (mine : NameSet) (n : Name) :
    StateT (Environment × NameSet) (Except String) Unit := do
  if (← get).2.contains n || !mine.contains n then return
  modify fun (e, done) => (e, done.insert n)
  let some ci := src.find? n | throw s!"{n}: not found"
  for dep in ci.getUsedConstantsAsSet do
    replay src mine dep
  let decl ← liftM (m := Except String) (toDeclaration n ci)
  let (env, done) ← get
  match env.addDeclCore 0 4096 decl none with
  | .ok env' => set (env', done)
  | .error _ => throw s!"{n}: rejected by the kernel"

def result (ok confirms : Bool) (reason : String) (axioms : Array Name := #[]) : Json :=
  Json.mkObj [("ok", toJson ok), ("confirms", toJson confirms), ("reason", toJson reason),
              ("axioms", toJson (axioms.map toString))]

def check (args : Args) : IO Json := do
  let env ← importModules #[{ module := evidenceModule }] {}
  let some idx := env.getModuleIdx? evidenceModule
    | return result false false "the evidence module is missing"
  let mine : NameSet := env.constants.fold (init := {}) fun acc n _ =>
    if env.getModuleIdxFor? n == some idx then acc.insert n else acc
  unless mine.contains evidenceTheorem do
    return result false false s!"the evidence file must prove a theorem `{evidenceTheorem}`"
  let base ← importModules env.header.moduleData[idx]!.imports {}
  let replayed := (mine.toList.forM (replay env mine)).run (base, {})
  let checked ← match replayed with
    | .error msg => return result false false msg
    | .ok (_, (e, _)) => pure e
  let axioms := axiomsOf checked evidenceTheorem
  let extra := axioms.filter (!standardAxioms.contains ·)
  unless extra.isEmpty do
    return result false false s!"non-standard axioms: {extra.toList}" axioms
  if args.kind != "vacuity" then
    return result true false "valid proof; its relevance is judged by a PVV" axioms
  let some target := checked.find? args.target
    | return result true false s!"unknown target {args.target}" axioms
  let some evidence := checked.find? evidenceTheorem
    | return result false false "evidence theorem vanished"
  let ctx : Core.Context := { fileName := "<dpc-evidence>", fileMap := default }
  let st : Core.State := { env := checked }
  let isVacuity? : MetaM (Option Bool) := do
    let some goal ← vacuityGoal target.type | return none
    isDefEq evidence.type goal
  let (verdict, _) ← (isVacuity?.run').toIO ctx st
  let reason := match verdict with
    | none => s!"{args.target} has no hypotheses that could be contradictory"
    | some false => s!"`{evidenceTheorem}` does not state the vacuity of {args.target}"
    | some true => s!"the hypotheses of {args.target} are contradictory"
  return result true (verdict == some true) reason axioms

def main (argv : List String) : IO UInt32 := do
  let args ← match parseArgs argv {} with
    | .ok a => pure a
    | .error e => do IO.eprintln e; return 2
  let some out := args.out | do IO.eprintln "usage: dpc-evidence --target NAME --kind KIND --out FILE"; return 2
  initSearchPath (← findSysroot)
  let json ← try check args catch e => pure (result false false s!"check failed: {e}")
  IO.FS.writeFile out (json.compress ++ "\n")
  return 0
