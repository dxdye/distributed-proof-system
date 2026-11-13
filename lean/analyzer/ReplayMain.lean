import Lean.Replay
import Lean.Data.Json
import Lean.Util.Path

/-!
`dpc-replay`: sends every declaration of the submission's own modules through
the kernel again (docs/adr/0009).

Lean does not re-check `.olean` files on import. The build of a submission runs
its code, so the `.olean` files of its modules may contain declarations the
kernel never saw (`debug.skipKernelTC`, `addDecl` from meta code, or files
written directly).

**Which modules.** The import closure of the roots is loaded once, without
environment extensions, so no initializer runs. Every module is classified by
the search path entry it is actually loaded from, not by its name:
* `core`: the toolchain's library,
* `trusted`: a directory passed with `--trusted` (the official packages, whose
  files the pipeline has verified against its snapshot),
* `replayed`: anything else.

A trusted module that imports a replayed one is an error, because loading it
would bring unchecked declarations into the trusted base.

**How.** Each replayed module is checked by a separate process
(`dpc-replay --check M`). The process imports the module's imports and replays
all of the module's constants into that environment with
`Lean.Environment.replay`. Inductive types are re-added, and their constructors
and recursors are compared with the ones the kernel generates. One process per
module keeps the `.olean` files memory-mapped and shared through the page
cache. Several environments in one process would each hold a private copy.
`--jobs` bounds the parallelism.

By induction over the module graph this checks everything that is not
trusted: each replayed module is checked against its imports, and each import
is either trusted or replayed itself.

Unsafe and partial constants are skipped, as in the kernel replay of Lean core.
Safe declarations cannot use them, so skipping does not open a gap.

Output: JSON Lines, schema `dpc.replay/1`: a header, then one record per module
of the closure, in import order.
-/

open Lean

def schema : String := "dpc.replay/1"

structure Args where
  roots : Array Name := #[]
  trusted : Array System.FilePath := #[]
  jobs : Nat := 4
  out : Option System.FilePath := none
  check : Option Name := none

def parseArgs : List String → Args → Except String Args
  | [], a => .ok a
  | "--root" :: v :: rest, a => parseArgs rest { a with roots := a.roots.push v.toName }
  | "--trusted" :: v :: rest, a => parseArgs rest { a with trusted := a.trusted.push v }
  | "--jobs" :: v :: rest, a =>
    match v.toNat? with
    | some n => if n == 0 then .error "--jobs must be positive" else parseArgs rest { a with jobs := n }
    | none => .error s!"--jobs expects a number, got '{v}'"
  | "--out" :: v :: rest, a => parseArgs rest { a with out := some v }
  | "--check" :: v :: rest, a => parseArgs rest { a with check := some v.toName }
  | x :: _, _ => .error s!"unexpected argument '{x}'"

def usage : String :=
  "usage: dpc-replay --root MODULE [--root MODULE ...] [--trusted DIR ...] [--jobs N] --out FILE\n" ++
  "       dpc-replay --check MODULE"

def truncate (s : String) (n : Nat := 2000) : String :=
  if s.length ≤ n then s else (s.take n).toString ++ " …"

/-! ## Worker: one module -/

/-- Replay the constants of `mod` into the environment of its imports. -/
def checkModule (mod : Name) : IO Json := do
  let mFile ← findOLean mod
  -- Modules of the module system come in parts; the last one holds all constants.
  let mut fnames := #[mFile]
  let sFile := OLeanLevel.server.adjustFileName mFile
  if ← sFile.pathExists then
    fnames := fnames.push sFile
    let pFile := OLeanLevel.private.adjustFileName mFile
    if ← pFile.pathExists then
      fnames := fnames.push pFile
  let parts ← readModuleDataParts fnames
  let some (header, _) := parts[0]? | throw <| IO.userError "no module data"
  let some (data, _) := parts.back? | throw <| IO.userError "no module data"
  unless data.constNames.size == data.constants.size do
    throw <| IO.userError "module data lists a different number of names and constants"
  let mut consts : Std.HashMap Name ConstantInfo := {}
  let mut skipped := 0
  for n in data.constNames, ci in data.constants do
    -- Importers look constants up by the listed name: it must be the real one.
    unless n == ci.name do
      throw <| IO.userError s!"module data lists {n} for the constant {ci.name}"
    if consts.contains n then
      throw <| IO.userError s!"module data lists {n} twice"
    consts := consts.insert n ci
    if ci.isUnsafe || ci.isPartial then
      skipped := skipped + 1
  let base ← importModules header.imports {}
  discard <| base.replay consts
  return Json.mkObj [("ok", toJson true), ("constants", toJson consts.size),
                     ("skipped", toJson skipped)]

def failure (msg : String) : Json :=
  Json.mkObj [("ok", toJson false), ("error", toJson (truncate msg))]

/-! ## Coordinator: closure, classification, workers -/

/-- The search path entry `findOLean` resolves `mod` to (same rule as
`Lean.SearchPath.findWithExt`: the first entry containing the root name). -/
def resolveEntry (sp : SearchPath) (mod : Name) : IO (Option System.FilePath) := do
  let pkg := mod.getRoot.toString (escape := false)
  sp.findM? fun p => (p / pkg).isDir <||> ((p / pkg).addExtension "olean").pathExists

def runWorker (self : System.FilePath) (mod : Name) : IO Json := do
  let out ← IO.Process.output
    { cmd := self.toString, args := #["--check", mod.toString (escape := false)] }
  let lines := (out.stdout.splitOn "\n").filter (· ≠ "")
  match lines.getLast? with
  | some line =>
    match Json.parse line with
    | .ok j => if out.exitCode == 0 then return j
               else return failure s!"checker exited with {out.exitCode}: {out.stderr}"
    | .error _ => return failure s!"checker exited with {out.exitCode}: {out.stderr}"
  | none => return failure s!"checker exited with {out.exitCode}: {out.stderr}"

def field (j : Json) (key : String) : Json := (j.getObjVal? key).toOption.getD Json.null

def replayAll (args : Args) (out : System.FilePath) : IO UInt32 := do
  if args.roots.isEmpty then
    IO.eprintln usage
    return 2
  let sp ← searchPathRef.get
  let core := (← getLibDir (← findSysroot)).normalize
  let trusted := args.trusted.map (·.normalize)
  let env ← importModules (args.roots.map ({ module := · })) {}
  let names := env.header.moduleNames
  let data := env.header.moduleData
  let mut origin : Std.HashMap Name String := {}
  let mut entry : Std.HashMap Name String := {}
  for name in names do
    let some e ← resolveEntry sp name
      | throw <| IO.userError s!"module {name} is not on the search path"
    let n := e.normalize
    let o := if n == core then "core" else if trusted.contains n then "trusted" else "replayed"
    origin := origin.insert name o
    entry := entry.insert name e.toString
  let todo := names.filter (origin[·]? == some "replayed")
  let mut chunks : Array (Array Name) := Array.replicate args.jobs #[]
  for h : i in [0:todo.size] do
    chunks := chunks.modify (i % args.jobs) (·.push todo[i])
  let self ← IO.appPath
  let tasks ← chunks.mapM fun chunk =>
    IO.asTask (prio := .dedicated) (chunk.mapM fun m => return (m, ← runWorker self m))
  let mut results : Std.HashMap Name Json := {}
  for t in tasks do
    for (m, j) in ← IO.ofExcept t.get do
      results := results.insert m j
  let headerRec := Json.mkObj [
    ("kind", toJson "header"), ("schema", toJson schema), ("toolchain", toJson Lean.versionString),
    ("roots", toJson (args.roots.map (·.toString))),
    ("trusted", toJson (args.trusted.map (·.toString))), ("core", toJson core.toString),
    ("jobs", toJson args.jobs)]
  let mut lines := #[headerRec.compress]
  for h : i in [0:names.size] do
    let name := names[i]
    let o := origin[name]?.getD "replayed"
    let mut ok := true
    let mut error : Option String := none
    let mut constants := (data[i]?.map (·.constants.size)).getD 0
    let mut skipped := 0
    if o == "replayed" then
      let r := results[name]?.getD (failure "not checked")
      ok := (field r "ok").getBool?.toOption.getD false
      error := (field r "error").getStr?.toOption
      constants := (field r "constants").getNat?.toOption.getD 0
      skipped := (field r "skipped").getNat?.toOption.getD 0
    else
      -- A trusted module must not pull unchecked declarations into the base.
      for imp in (data[i]?.map (·.imports)).getD #[] do
        if origin[imp.module]? == some "replayed" then
          ok := false
          error := some s!"trusted module imports {imp.module} from an untrusted location"
    lines := lines.push (Json.mkObj [
      ("kind", toJson "module"), ("module", toJson name.toString), ("origin", toJson o),
      ("entry", toJson (entry[name]?.getD "")), ("constants", toJson constants),
      ("skipped", toJson skipped), ("ok", toJson ok),
      ("error", match error with | some e => toJson e | none => Json.null)]).compress
  IO.FS.writeFile out ("\n".intercalate lines.toList ++ "\n")
  return 0

def main (argv : List String) : IO UInt32 := do
  let args ← match parseArgs argv {} with
    | .ok a => pure a
    | .error e => do IO.eprintln s!"{e}\n{usage}"; return 2
  initSearchPath (← findSysroot)
  if let some mod := args.check then
    let json ← try checkModule mod catch e => pure (failure (toString e))
    IO.println json.compress
    return 0
  let some out := args.out | do IO.eprintln usage; return 2
  try replayAll args out
  catch e => do
    IO.eprintln s!"dpc-replay: {e}"
    return 1
