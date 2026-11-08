import Lean
import DpcAnalyzer.Classify
import DpcAnalyzer.Closure
import DpcAnalyzer.Digest

/-!
# JSON Lines export (interface I-2)

Line 1 is a `header` record, every further line a `decl` record. The schema is
mirrored on the Python side in `dpc/analysis/model.py`; bump `schemaVersion`
on any incompatible change.

Exported declarations: `TCB(T)` (including its hardened part, so that reach
`R(d)` can later be computed across Mathlib) and `Dep(T) \ H` plus its hardened
frontier. Full dependency lists are only exported for non-hardened
declarations to keep the file small.

## Two modes (see docs/adr/0004)

* `core`: no environment extensions are loaded, hence no foreign code runs.
  Everything here is derived from the kernel's constant map alone: closures,
  hashes, axioms. This output is authoritative.
* `metadata`: extensions are loaded (running the imported modules'
  `initialize` blocks). Adds source ranges and flags such as `noncomputable`
  and `instance`, and refines ticket units via matcher/projection info. Foreign
  code could tamper with this run, so the pipeline cross-checks it against the
  `core` run and uses it only for presentation.
-/

open Lean

namespace DpcAnalyzer

/-- v2: SHA-256 Merkle digests for types and definition bodies, `proof_hash`. -/
def schemaVersion : String := "dpc.analysis/2"

/-- Root namespaces treated as hardened (`H`) unless disabled on the CLI. -/
def defaultHardenedPrefixes : Array Name :=
  #[`Init, `Std, `Lean, `Lake, `Mathlib, `Batteries, `Aesop, `Qq, `ProofWidgets,
    `Plausible, `ImportGraph, `LeanSearchClient]

inductive Mode where
  | core
  | metadata
  deriving BEq

def Mode.toString : Mode → String
  | .core => "core"
  | .metadata => "metadata"

structure Config where
  root : Name
  imports : Array Name
  hardenedPrefixes : Array Name
  mode : Mode

/-- Deduplicated, sorted names — output must be deterministic. -/
def sortedNames (ns : Array Name) : Array Name :=
  (ns.foldl (·.insert ·) ({} : NameSet)).toArray.qsort Name.lt

/-- All axioms `T` depends on, found by walking the full dependency closure.

Deliberately does not use `Lean.collectAxioms`: that function trusts axiom
lists precomputed inside imported `.olean` files, which a malicious build
could have forged. -/
def axiomsOf (env : Environment) (root : Name) : Array Name :=
  let dep := reach env allEdges (fun _ => true) [root]
  sortedNames <| dep.toArray.filter fun n =>
    match env.find? n with
    | some (.axiomInfo _) => true
    | _ => false

private def nameJson (n : Name) : Json := toJson (toString n)

private def namesJson (ns : Array Name) : Json := Json.arr (ns.map nameJson)

private def optJson (o : Option Json) : Json := o.getD Json.null

def headerRecord (cfg : Config) (axioms : Array Name) : Json :=
  Json.mkObj [
    ("kind", toJson "header"),
    ("schema", toJson schemaVersion),
    ("mode", toJson cfg.mode.toString),
    ("root", nameJson cfg.root),
    ("imports", namesJson cfg.imports),
    ("toolchain", toJson Lean.versionString),
    ("hardened_prefixes", namesJson cfg.hardenedPrefixes),
    ("axioms", namesJson axioms)]

/-- Fields every mode can compute from the constant map alone. -/
def coreFields (env : Environment) (hardened : Name → Bool) (inTcb : Bool) (n : Name)
    (ci : ConstantInfo) : List (String × Json) :=
  let isH := hardened n
  [ ("kind", toJson "decl"),
    ("name", nameJson n),
    ("display_name", nameJson (privateToUserName n)),
    ("decl_kind", toJson (declKind ci)),
    ("module", optJson ((moduleOf? env n).map nameJson)),
    ("unit", nameJson (ticketUnit env n)),
    ("hardened", toJson isH),
    ("in_tcb", toJson inTcb),
    ("tcb_deps", namesJson (sortedNames (tcbEdges ci))),
    ("all_deps", if isH then Json.null else namesJson (sortedNames (allEdges ci))),
    -- Meaning: SHA-256 Merkle digests (forgery-resistant, used by the graph diff).
    ("type_hash", toJson (Digest.hexDigest ci.type)),
    ("value_hash", match ci with
      | .defnInfo v => toJson (Digest.hexDigest v.value)
      | _ => Json.null),
    -- Proof terms and opaque bodies do not affect meaning (proof irrelevance, the
    -- kernel never unfolds opaque bodies); a cheap structural hash suffices to
    -- notice proof-only changes, which matter for class B only.
    ("proof_hash", match ci with
      | .thmInfo v => toJson (toString v.value.hash)
      | .opaqueInfo v => toJson (toString v.value.hash)
      | _ => Json.null) ]

/-- Presentation metadata; needs loaded environment extensions. -/
def metadataFields (env : Environment) (hardened : Name → Bool) (n : Name)
    (ci : ConstantInfo) : CoreM (List (String × Json)) := do
  let range ← if hardened n then pure none else findDeclarationRanges? n
  let rangeJson := range.map fun r =>
    Json.mkObj [("start_line", toJson r.range.pos.line),
                ("end_line", toJson r.range.endPos.line)]
  let flags := Json.mkObj [
    ("private", toJson (isPrivateName n)),
    ("noncomputable", toJson (isNoncomputable env n)),
    ("instance", toJson (Meta.isInstanceCore env n)),
    ("unsafe", toJson ci.isUnsafe),
    ("partial", toJson ci.isPartial)]
  return [("range", optJson rangeJson), ("flags", flags)]

/-- Analyse `cfg.root` in `env` and return all JSON Lines records. -/
def analyze (cfg : Config) (env : Environment) : IO (Array Json) := do
  -- See all bodies, including those not exported by the module system.
  let env := env.setExporting false
  unless env.contains cfg.root do
    throw <| IO.userError s!"root declaration '{cfg.root}' not found in the imported modules"
  let hardened := isHardened env cfg.hardenedPrefixes
  let tcbSet := tcb env cfg.root
  let depSet := depNew env hardened cfg.root
  let names := sortedNames (tcbSet.toArray ++ depSet.toArray)
  let ctx : Core.Context := { fileName := "<dpc-analyze>", fileMap := default }
  let st : Core.State := { env }
  let run : CoreM (Array Json) := do
    let mut out := #[headerRecord cfg (axiomsOf env cfg.root)]
    for n in names do
      let some ci := env.find? n | continue
      let base := coreFields env hardened (tcbSet.contains n) n ci
      let extra ← if cfg.mode == .metadata then metadataFields env hardened n ci else pure []
      out := out.push (Json.mkObj (base ++ extra))
    return out
  let (lines, _) ← run.toIO ctx st
  return lines

end DpcAnalyzer
