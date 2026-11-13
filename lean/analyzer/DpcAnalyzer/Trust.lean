import Lean

/-!
Trust by location (docs/adr/0009): a module is trusted if it is loaded from
the toolchain's library or from a directory the caller trusts (the official
packages, verified against the pipeline's snapshot), regardless of its name.
-/

open Lean

namespace DpcAnalyzer.Trust

/-- The search path entry `findOLean` resolves `mod` to (same rule as
`Lean.SearchPath.findWithExt`: the first entry containing the root name). -/
def resolveEntry (sp : SearchPath) (mod : Name) : IO (Option System.FilePath) := do
  let pkg := mod.getRoot.toString (escape := false)
  sp.findM? fun p => (p / pkg).isDir <||> ((p / pkg).addExtension "olean").pathExists

inductive Origin where
  | core | trusted | untrusted
  deriving BEq, Repr

def Origin.toString : Origin → String
  | .core => "core" | .trusted => "trusted" | .untrusted => "replayed"

structure Classifier where
  sp : SearchPath
  core : System.FilePath
  trusted : Array System.FilePath

def Classifier.mk' (trusted : Array System.FilePath) : IO Classifier := do
  return { sp := ← searchPathRef.get, core := (← getLibDir (← findSysroot)).normalize,
           trusted := trusted.map (·.normalize) }

/-- Origin and search path entry of a module. -/
def Classifier.classify (c : Classifier) (mod : Name) : IO (Origin × System.FilePath) := do
  let some e ← resolveEntry c.sp mod
    | throw <| IO.userError s!"module {mod} is not on the search path"
  let n := e.normalize
  let o := if n == c.core then Origin.core else if c.trusted.contains n then .trusted else .untrusted
  return (o, e)

/-- All parts of a module's `.olean` (module system: the last part holds all
constants). Reading them runs no code of the module. -/
def readParts (mod : Name) : IO (Array (ModuleData × CompactedRegion)) := do
  let mFile ← findOLean mod
  let mut fnames := #[mFile]
  let sFile := OLeanLevel.server.adjustFileName mFile
  if ← sFile.pathExists then
    fnames := fnames.push sFile
    let pFile := OLeanLevel.private.adjustFileName mFile
    if ← pFile.pathExists then
      fnames := fnames.push pFile
  readModuleDataParts fnames

end DpcAnalyzer.Trust
