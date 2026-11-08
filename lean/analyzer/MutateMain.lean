import DpcAnalyzer
import DpcAnalyzer.Mutate

/-!
`dpc-mutate`: generates type-correct mutants of declarations and runs the local
equivalence filter (concept §5.1, SR-07). Output: JSON Lines, schema
`dpc.mutants/1`, one record per candidate mutant (rejected ones included, so
the filter rates can be measured — verification §11.2).

Loads environment extensions (simp sets, notation, delaborators), i.e. runs the
imported modules' initializers: sandbox only (SR-20).
-/

open Lean Meta Elab DpcAnalyzer DpcAnalyzer.Mutate

def usage : String :=
  "usage: dpc-mutate --import MODULE [...] --decl NAME [...] [--tactic SCRIPT ...] " ++
  "[--heartbeats N] [--max-sites N] --out FILE"

/-- Scripts tried on the closed equivalence goal `∀ ctx, a ↔ a'` (or `= `). -/
def defaultScripts : Array String := #[
  "intros; rfl",
  "intros; decide",
  "intros; omega",
  "intros; simp",
  "intros; simp_all",
  "intros; constructor <;> intro <;> omega",
  "intros; assumption"]

structure Args where
  imports : Array Name := #[]
  decls : Array Name := #[]
  scripts : Array String := #[]
  heartbeats : Nat := 20000
  maxSites : Nat := 64
  out : Option System.FilePath := none

def parseArgs : List String → Args → Except String Args
  | [], a => .ok a
  | "--import" :: v :: rest, a => parseArgs rest { a with imports := a.imports.push v.toName }
  | "--decl" :: v :: rest, a => parseArgs rest { a with decls := a.decls.push v.toName }
  | "--tactic" :: v :: rest, a => parseArgs rest { a with scripts := a.scripts.push v }
  | "--heartbeats" :: v :: rest, a => parseArgs rest { a with heartbeats := v.toNat! }
  | "--max-sites" :: v :: rest, a => parseArgs rest { a with maxSites := v.toNat! }
  | "--out" :: v :: rest, a => parseArgs rest { a with out := some v }
  | x :: _, _ => .error s!"unexpected argument '{x}'"

@[implemented_by enableInitializersExecution]
opaque allowInitializers : BaseIO Unit

def pp (e : Expr) : MetaM String := return toString (← ppExpr e)

/-- Mutants of one declaration as JSON records. -/
def mutantsOf (name : Name) (args : Args) : TermElabM (Array Json) := do
  let env ← getEnv
  let some ci := env.find? name | throwError "unknown declaration {name}"
  let scripts := if args.scripts.isEmpty then defaultScripts else args.scripts
  let mut candidates : Array (Target × Mutation) := #[]
  for m in ← siteMutations env ci.type args.maxSites do
    candidates := candidates.push (.type, m)
  for m in ← telescopeMutations ci.type do
    candidates := candidates.push (.type, m)
  if let .defnInfo v := ci then
    for m in ← siteMutations env v.value args.maxSites do
      candidates := candidates.push (.value, m)
  let sort ← inferType ci.type
  let mut out := #[]
  for (target, m) in candidates do
    let original := if target == .type then ci.type else ci.value?.getD ci.type
    let expected := if target == .type then sort else ci.type
    let ok ← typeChecks m.result (some expected)
    let proof ← if ok then proveWith m.goal scripts args.heartbeats else pure none
    out := out.push <| Json.mkObj [
      ("kind", toJson "mutant"),
      ("decl", toJson (toString name)),
      ("target", toJson target.toString),
      ("operator", toJson m.operator),
      ("detail", toJson m.detail),
      ("type_correct", toJson ok),
      ("equivalent", if ok then toJson proof.isSome else Json.null),
      ("proof_script", (proof.map toJson).getD Json.null),
      ("original", toJson (← pp original)),
      ("mutant", toJson (← pp m.result)),
      ("mutant_hash", toJson (toString m.result.hash))]
  return out

def main (argv : List String) : IO UInt32 := do
  let args ← match parseArgs argv {} with
    | .ok a => pure a
    | .error e => do
      IO.eprintln s!"{e}\n{usage}"
      return 2
  let some out := args.out | do IO.eprintln usage; return 2
  if args.imports.isEmpty || args.decls.isEmpty then
    IO.eprintln usage
    return 2
  initSearchPath (← findSysroot)
  allowInitializers
  let env ← importModules (args.imports.map fun m => { module := m }) {} (loadExts := true)
  let env := env.setExporting false
  let header := Json.mkObj [
    ("kind", toJson "header"), ("schema", toJson "dpc.mutants/1"),
    ("toolchain", toJson Lean.versionString),
    ("imports", toJson (args.imports.map toString)),
    ("heartbeats", toJson args.heartbeats)]
  let ctx : Core.Context := { fileName := "<dpc-mutate>", fileMap := default }
  let st : Core.State := { env }
  let run : CoreM (Array Json) := do
    let mut lines := #[header]
    for name in args.decls do
      lines := lines ++ (← (mutantsOf name args).run'.run')
    return lines
  let (lines, _) ← run.toIO ctx st
  IO.FS.writeFile out (String.intercalate "\n" (lines.toList.map Json.compress) ++ "\n")
  IO.println s!"dpc-mutate: wrote {lines.size - 1} mutants to {out}"
  return 0
