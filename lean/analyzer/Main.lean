import DpcAnalyzer

/-!
`dpc-analyze`: extracts axioms, `TCB(T)` and `Dep(T) \ H` of a root
declaration and writes them as JSON Lines.

The search path is taken from `LEAN_PATH` (built `.olean` files of the
analysed repository and its packages) and `LEAN_SYSROOT` (core library).

**Security:** `--metadata` loads environment extensions, which runs the
`initialize` blocks of every imported module, i.e. foreign code. The default
`core` mode runs no foreign code. Both modes still read foreign `.olean` files
and therefore run inside the sandbox (SR-20).
-/

open Lean DpcAnalyzer

def usage : String :=
  "usage: dpc-analyze --root NAME --import MODULE [--import MODULE ...] " ++
  "[--hardened PREFIX ...] [--no-default-hardened] [--metadata] --out FILE"

structure Args where
  root : Option Name := none
  imports : Array Name := #[]
  hardened : Array Name := #[]
  defaultHardened : Bool := true
  metadata : Bool := false
  out : Option System.FilePath := none

def parseArgs : List String → Args → Except String Args
  | [], a => .ok a
  | "--root" :: v :: rest, a => parseArgs rest { a with root := some v.toName }
  | "--import" :: v :: rest, a => parseArgs rest { a with imports := a.imports.push v.toName }
  | "--hardened" :: v :: rest, a => parseArgs rest { a with hardened := a.hardened.push v.toName }
  | "--no-default-hardened" :: rest, a => parseArgs rest { a with defaultHardened := false }
  | "--metadata" :: rest, a => parseArgs rest { a with metadata := true }
  | "--out" :: v :: rest, a => parseArgs rest { a with out := some v }
  | x :: _, _ => .error s!"unexpected argument '{x}'"

/-- Runs `initialize` blocks of imported modules (foreign code, see module doc). -/
@[implemented_by enableInitializersExecution]
opaque allowInitializers : BaseIO Unit

def main (argv : List String) : IO UInt32 := do
  let args ← match parseArgs argv {} with
    | .ok a => pure a
    | .error e => do
      IO.eprintln s!"{e}\n{usage}"
      return 2
  let (some root, some out) := (args.root, args.out)
    | do IO.eprintln usage; return 2
  if args.imports.isEmpty then
    IO.eprintln usage
    return 2
  let base := if args.defaultHardened then defaultHardenedPrefixes else #[]
  let mode := if args.metadata then Mode.metadata else Mode.core
  let cfg : Config :=
    { root, imports := args.imports, hardenedPrefixes := base ++ args.hardened, mode }
  initSearchPath (← findSysroot)
  if args.metadata then allowInitializers
  let env ← importModules (args.imports.map fun m => { module := m }) {}
    (loadExts := args.metadata)
  let lines ← analyze cfg env
  IO.FS.writeFile out (String.intercalate "\n" (lines.toList.map Json.compress) ++ "\n")
  IO.println s!"dpc-analyze: wrote {lines.size - 1} declarations to {out} ({mode.toString})"
  return 0
