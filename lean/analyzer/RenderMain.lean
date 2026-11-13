import DpcAnalyzer.Render
import DpcAnalyzer.ExprJson
import DpcAnalyzer.Trust
import DpcAnalyzer.Latex

/-!
`dpc-render`: the ticket views once more, **without** the submission's
display rules (docs/adr/0011).

A submission can bring its own notation, coercions, unexpanders and
delaborators, and `dpc-mutate --render` shows its declarations with them.
That is usually more readable. It also lets a submission decide what reviewers
see, e.g. print `a ≤ b` as `a < b`. This program renders the same components
in an environment that contains the extensions of the toolchain and the
official packages only:

1. It walks the import graph from the roots. Modules are classified by where
   they are loaded from (`DpcAnalyzer.Trust`). Untrusted modules are only
   *read* as data, so none of their code runs and none of their extensions is
   loaded.
2. It imports the trusted modules the untrusted ones depend on, with their
   environment extensions (Lean, Mathlib).
3. It adds every untrusted constant a component mentions, as an axiom with its
   type: rendering needs no more, and the kernel replay (ADR 0009) has
   checked the declarations.
4. It renders the components of each `--decl` and, with `--mutants`, the
   mutated expression of every encoded mutant (`DpcAnalyzer.ExprJson`). It uses
   the same `pp` and glossary as `dpc-mutate`.

Output: JSON Lines with `trusted_view` and `trusted_mutant` records.
-/

open Lean Meta DpcAnalyzer DpcAnalyzer.Render DpcAnalyzer.Trust DpcAnalyzer.Mutate

structure Args where
  roots : Array Name := #[]
  trusted : Array System.FilePath := #[]
  decls : Array Name := #[]
  mutants : Option System.FilePath := none
  out : Option System.FilePath := none

def parseArgs : List String → Args → Except String Args
  | [], a => .ok a
  | "--root" :: v :: rest, a => parseArgs rest { a with roots := a.roots.push v.toName }
  | "--trusted" :: v :: rest, a => parseArgs rest { a with trusted := a.trusted.push v }
  | "--decl" :: v :: rest, a => parseArgs rest { a with decls := a.decls.push v.toName }
  | "--mutants" :: v :: rest, a => parseArgs rest { a with mutants := some v }
  | "--out" :: v :: rest, a => parseArgs rest { a with out := some v }
  | x :: _, _ => .error s!"unexpected argument '{x}'"

def usage : String :=
  "usage: dpc-render --root MODULE [...] [--trusted DIR ...] [--decl NAME ...] " ++
  "[--mutants FILE] --out FILE"

@[implemented_by enableInitializersExecution]
opaque allowInitializers : BaseIO Unit

structure Loaded where
  /-- Trusted modules that untrusted ones import directly. -/
  frontier : Array Name := #[]
  /-- Constants of the untrusted modules, read as data. -/
  untrusted : Std.HashMap Name ConstantInfo := {}

/-- Walk the import graph. Trusted modules are not opened here; untrusted ones
are read as data only. -/
def walk (c : Classifier) (roots : Array Name) : IO Loaded := do
  let mut seen : NameSet := {}
  let mut todo := roots.toList
  let mut out : Loaded := {}
  while !todo.isEmpty do
    let m := todo.head!
    todo := todo.tail!
    if seen.contains m then continue
    seen := seen.insert m
    let (origin, _) ← c.classify m
    if origin != .untrusted then
      out := { out with frontier := out.frontier.push m }
      continue
    let parts ← readParts m
    let some (header, _) := parts[0]? | throw <| IO.userError s!"{m}: no module data"
    let some (data, _) := parts.back? | throw <| IO.userError s!"{m}: no module data"
    let mut consts := out.untrusted
    for n in data.constNames, ci in data.constants do
      unless n == ci.name do
        throw <| IO.userError s!"{m}: module data lists {n} for the constant {ci.name}"
      consts := consts.insert n ci
    out := { out with untrusted := consts }
    todo := header.imports.toList.map (·.module) ++ todo
  return out

/-- Make `n` known to the environment as an axiom, after the untrusted
constants its type mentions. -/
partial def ensure (untrusted : Std.HashMap Name ConstantInfo) (n : Name)
    (busy : NameSet := {}) : CoreM Unit := do
  if (← getEnv).contains n then return
  let some ci := untrusted[n]? | return  -- not a constant of the submission
  if busy.contains n then throwError "cyclic types at {n}"
  for d in ci.type.getUsedConstants do
    ensure untrusted d (busy.insert n)
  let decl := Declaration.axiomDecl
    { name := n, levelParams := ci.levelParams, type := ci.type, isUnsafe := ci.isUnsafe }
  match (← getEnv).addDeclCore 0 4096 decl none with
  | .ok env => setEnv env
  | .error e => throwError "cannot add {n}: {← (e.toMessageData {}).toString}"

def ensureAll (untrusted : Std.HashMap Name ConstantInfo) (e : Expr) : CoreM Unit :=
  for d in e.getUsedConstants do ensure untrusted d

def errorRecord (what : String) (e : Exception) : CoreM Json :=
  return Json.mkObj [("kind", toJson "error"), ("item", toJson what),
                     ("error", toJson (← e.toMessageData.toString))]

def viewRecord (loaded : Loaded) (name : Name) : CoreM Json := do
  let env ← getEnv
  let lookup := fun n => loaded.untrusted[n]? <|> env.find? n
  let some ci := lookup name | throwError "unknown declaration {name}"
  let mut comps := #[]
  for (target, label, e) in components lookup ci do
    ensureAll loaded.untrusted e
    let comp ← (componentJson target label e name).run'
    let tex ← (Latex.typeset e).run'
    comps := comps.push (comp.setObjVal! "latex" ((tex.map toJson).getD Json.null))
  return Json.mkObj [("kind", toJson "trusted_view"), ("decl", toJson (toString name)),
                     ("components", Json.arr comps)]

def mutantRecord (loaded : Loaded) (m : Json) : CoreM (Option Json) := do
  let some expr := (m.getObjVal? "expr").toOption | return none
  if expr.isNull then return none
  let e ← match ExprJson.ofJson' expr with
    | .ok e => pure e
    | .error msg => throwError "cannot decode the mutant: {msg}"
  let decl := ((m.getObjValAs? String "decl").toOption.getD "").toName
  ensureAll loaded.untrusted e
  let text ← (pp e).run'
  let gloss ← (glossary e decl).run'
  let tex ← (Latex.typeset e).run'
  let field := fun (k : String) => (m.getObjVal? k).toOption.getD Json.null
  return some <| Json.mkObj [
    ("kind", toJson "trusted_mutant"), ("decl", field "decl"), ("target", field "target"),
    ("component", field "component"), ("mutant_hash", field "mutant_hash"),
    ("text", toJson text), ("glossary", gloss), ("latex", (tex.map toJson).getD Json.null)]

def main (argv : List String) : IO UInt32 := do
  let args ← match parseArgs argv {} with
    | .ok a => pure a
    | .error e => do IO.eprintln s!"{e}\n{usage}"; return 2
  let some out := args.out | do IO.eprintln usage; return 2
  if args.roots.isEmpty then
    IO.eprintln usage
    return 2
  initSearchPath (← findSysroot)
  let c ← Classifier.mk' args.trusted
  let loaded ← walk c args.roots
  -- Only now may code run: the trusted modules' initializers.
  allowInitializers
  let env ← importModules (loaded.frontier.map ({ module := · })) {} (loadExts := true)
  let env := env.setExporting false
  for m in env.header.moduleNames do
    let (origin, _) ← c.classify m
    if origin == .untrusted then
      IO.eprintln s!"dpc-render: trusted modules import the untrusted module {m}"
      return 1
  let mutants ← match args.mutants with
    | some f => do
      let lines := (← IO.FS.lines f).filter (· ≠ "")
      lines.filterMapM fun l => pure (Json.parse l).toOption
    | none => pure #[]
  let header := Json.mkObj [
    ("kind", toJson "header"), ("schema", toJson "dpc.trusted-render/1"),
    ("toolchain", toJson Lean.versionString),
    ("roots", toJson (args.roots.map toString)),
    ("untrusted_constants", toJson loaded.untrusted.size)]
  let ctx : Core.Context := { fileName := "<dpc-render>", fileMap := default }
  let run : CoreM (Array Json) := do
    let mut lines := #[header]
    for name in args.decls do
      let one : CoreM Json := withCurrHeartbeats (viewRecord loaded name)
      lines := lines.push (← tryCatchRuntimeEx one (errorRecord (toString name)))
    for m in mutants do
      if (m.getObjValAs? String "kind").toOption != some "mutant" then continue
      let one : CoreM (Option Json) := withCurrHeartbeats (mutantRecord loaded m)
      let what := (m.getObjValAs? String "mutant_hash").toOption.getD "?"
      let rec_ ← tryCatchRuntimeEx one fun e => some <$> errorRecord what e
      if let some r := rec_ then lines := lines.push r
    return lines
  let (lines, _) ← run.toIO ctx { env }
  IO.FS.writeFile out (String.intercalate "\n" (lines.toList.map Json.compress) ++ "\n")
  IO.println s!"dpc-render: wrote {lines.size - 1} records to {out}"
  return 0
