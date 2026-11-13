import DpcAnalyzer
import DpcAnalyzer.Mutate
import DpcAnalyzer.Render
import DpcAnalyzer.ExprJson

/-!
`dpc-mutate`: generates type-correct mutants of declarations and runs the local
equivalence filter (concept §5.1, SR-07). Output: JSON Lines, schema
`dpc.mutants/1`, one record per candidate mutant (rejected ones included, so
the filter rates can be measured — verification §11.2).

With `--render` it instead writes one `view` record per declaration: the
components a reviewer sees (type, definition body, constructors), rendered by
the same `pp` as the mutants, with a glossary of the constants each component
uses (SR-21). Ticket views and honeypots are built from these records, so the
two cannot be told apart by their formatting (SR-06).

Loads environment extensions (simp sets, notation, delaborators), i.e. runs the
imported modules' initializers: sandbox only (SR-20). Usable mutants carry
their expression (`expr`, see `DpcAnalyzer.ExprJson`), so that `dpc-render` can
show them without the submission's display rules as well (docs/adr/0011).
-/

open Lean Meta Elab DpcAnalyzer DpcAnalyzer.Mutate DpcAnalyzer.Render

def usage : String :=
  "usage: dpc-mutate --import MODULE [...] --decl NAME [...] [--tactic SCRIPT ...] " ++
  "[--heartbeats N] [--max-sites N] [--render] --out FILE"

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
  render : Bool := false
  out : Option System.FilePath := none

def parseArgs : List String → Args → Except String Args
  | [], a => .ok a
  | "--import" :: v :: rest, a => parseArgs rest { a with imports := a.imports.push v.toName }
  | "--decl" :: v :: rest, a => parseArgs rest { a with decls := a.decls.push v.toName }
  | "--tactic" :: v :: rest, a => parseArgs rest { a with scripts := a.scripts.push v }
  | "--heartbeats" :: v :: rest, a => parseArgs rest { a with heartbeats := v.toNat! }
  | "--max-sites" :: v :: rest, a => parseArgs rest { a with maxSites := v.toNat! }
  | "--out" :: v :: rest, a => parseArgs rest { a with out := some v }
  | "--render" :: rest, a => parseArgs rest { a with render := true }
  | x :: _, _ => .error s!"unexpected argument '{x}'"

@[implemented_by enableInitializersExecution]
opaque allowInitializers : BaseIO Unit

/-- What is mutated in a declaration: `(target, label, original, expected type)`,
the components of `DpcAnalyzer.Render.components`. -/
def mutationTargets (env : Environment) (ci : ConstantInfo) :
    MetaM (Array (Target × String × Expr × Expr)) := do
  let mut out := #[]
  for (target, label, e) in components env.find? ci do
    let expected ← match target with
      | .value => pure ci.type
      | _ => inferType e
    out := out.push (target, label, e, expected)
  return out

/-- Largest encoded mutant expression handed to `dpc-render`. -/
def maxExprBytes : Nat := 1000000

/-- The mutant's expression for `dpc-render`, if it survives the round trip. -/
def encodedExpr (e : Expr) : Json :=
  match ExprJson.encodeChecked e with
  | .ok j => if j.compress.length ≤ maxExprBytes then j else Json.null
  | .error _ => Json.null

/-- The view of one declaration: every component a mutant could replace. -/
def viewOf (name : Name) : MetaM Json := do
  let env ← getEnv
  let some ci := env.find? name | throwError "unknown declaration {name}"
  let mut comps := #[]
  for (target, label, e) in components env.find? ci do
    comps := comps.push (← componentJson target label e name)
  return Json.mkObj [
    ("kind", toJson "view"), ("decl", toJson (toString name)),
    ("decl_kind", toJson (DpcAnalyzer.declKind ci)), ("components", Json.arr comps)]

/-- Mutants of one declaration as JSON records. -/
def mutantsOf (name : Name) (args : Args) : TermElabM (Array Json) := do
  let env ← getEnv
  let some ci := env.find? name | throwError "unknown declaration {name}"
  let scripts := if args.scripts.isEmpty then defaultScripts else args.scripts
  let isTheorem := match ci with | .thmInfo _ => true | _ => false
  let mut out := #[]
  for (target, label, original, expected) in ← mutationTargets env ci do
    let mut candidates := ← siteMutations env original args.maxSites
    if target != .value then  -- ∀-telescopes: statements and constructor fields
      candidates := candidates ++ (← telescopeMutations original)
    let originalText ← pp original
    let lintable := target != .value
    let originalLints ← if lintable then lints original isTheorem args.heartbeats
      else pure { vacuous := false, trivial := false }
    for m in candidates do
      let ok ← typeChecks m.result (some expected)
      -- 1. local equivalence (always meaningful)
      let mut proof ← if ok then proveWith m.goal scripts args.heartbeats else pure none
      let mut level : Option String := proof.map fun _ => "local"
      -- 2. component equivalence (definitions and structure fields only)
      if ok && proof.isNone && target != .type then
        let goal? ← match target with
          | .value => valueGoal original m.result
          | _ => fieldGoal original m.result
        if let some goal := goal? then
          proof ← proveWith goal scripts args.heartbeats
          level := proof.map fun _ => "component"
      -- 3. automatic detection (§5.2 checks) of the remaining candidates
      let detected ← if ok && proof.isNone && lintable then
          pure (autoDetected originalLints (← lints m.result isTheorem args.heartbeats))
        else pure none
      let mutantText ← pp m.result
      let usable := ok && proof.isNone && detected.isNone && mutantText != originalText
      -- The glossary of what the reviewer will see (only for usable mutants: pp is slow).
      let gloss ← if usable then glossary m.result name else pure (Json.arr #[])
      out := out.push <| Json.mkObj [
        ("kind", toJson "mutant"),
        ("decl", toJson (toString name)),
        ("target", toJson target.toString),
        ("component", toJson label),
        ("operator", toJson m.operator),
        ("detail", toJson m.detail),
        ("type_correct", toJson ok),
        ("equivalent", if ok then toJson proof.isSome else Json.null),
        ("equivalent_by", (level.map toJson).getD Json.null),
        ("proof_script", (proof.map toJson).getD Json.null),
        ("auto_detected", (detected.map toJson).getD Json.null),
        ("visible", toJson (mutantText != originalText)),
        ("original", toJson originalText),
        ("mutant", toJson mutantText),
        ("mutant_hash", toJson (toString m.result.hash)),
        ("glossary", gloss),
        ("expr", if usable then encodedExpr m.result else Json.null)]
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
      -- Each declaration gets the full heartbeat budget, and one that fails
      -- (e.g. a timeout while rendering) is reported instead of ending the run.
      let one : CoreM (Array Json) := withCurrHeartbeats do
        if args.render then return #[← (viewOf name).run']
        else (mutantsOf name args).run'.run'
      let records ← tryCatchRuntimeEx one fun e => do
        return #[Json.mkObj [("kind", toJson "error"), ("decl", toJson (toString name)),
                             ("error", toJson (← e.toMessageData.toString))]]
      lines := lines ++ records
    return lines
  let (lines, _) ← run.toIO ctx st
  IO.FS.writeFile out (String.intercalate "\n" (lines.toList.map Json.compress) ++ "\n")
  let what := if args.render then "views" else "mutants"
  IO.println s!"dpc-mutate: wrote {lines.size - 1} {what} to {out}"
  return 0
