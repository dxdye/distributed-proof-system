import Lean

/-!
# Classification of declarations

Coarse kinds, flags, and *ticket units*. A ticket unit is the user-facing
declaration a human reviews; compiler-generated auxiliaries (matchers,
`_proof_n`, `brecOn`, equation lemmas, …), constructors, recursors and
structure projections are folded into the declaration they belong to.
-/

open Lean

namespace DpcAnalyzer

/-- Coarse declaration kind, as exported to JSON. -/
def declKind : ConstantInfo → String
  | .axiomInfo _  => "axiom"
  | .defnInfo _   => "def"
  | .thmInfo _    => "theorem"
  | .opaqueInfo _ => "opaque"
  | .quotInfo _   => "quot"
  | .inductInfo _ => "inductive"
  | .ctorInfo _   => "ctor"
  | .recInfo _    => "recursor"

/-- The last name component is compiler-internal (`_proof_1`, `_unary`, numeric, …). -/
def lastComponentInternal : Name → Bool
  | .str _ s => s.startsWith "_"
  | .num _ _ => true
  | .anonymous => false

/-- Suffixes of automatically generated equation / induction lemmas. -/
def isGeneratedLemmaSuffix : Name → Bool
  | .str _ s =>
    s == "eq_def" || s == "eq_unfold" || s == "induct" || s == "mutual_induct"
      || s == "fun_cases" || s == "induct_unfolding"
      || (s.startsWith "eq_" && s.length > 3 && (s.toList.drop 3).all Char.isDigit)
  | _ => false


private def hasNumberedSuffix (s pre : String) : Bool :=
  s.startsWith pre && s.length > pre.length && (s.toList.drop pre.length).all Char.isDigit

/-- Name-based fallback for matchers and auxiliary proofs (`foo.match_1`,
`foo.proof_2`); needed in `core` mode where matcher info is not loaded. -/
def isAuxByName : Name → Bool
  | .str _ s => hasNumberedSuffix s "match_" || hasNumberedSuffix s "proof_"
  | _ => false

private def isDefn (env : Environment) (n : Name) : Bool :=
  match env.find? n with
  | some (.defnInfo _) => true
  | _ => false

/-- If `n` is an auxiliary declaration, the declaration it belongs to. -/
def auxParent? (env : Environment) (n : Name) : Option Name :=
  match env.find? n with
  | some (.ctorInfo v) => some v.induct
  | some (.recInfo _) => some n.getPrefix
  | _ =>
    if Meta.isMatcherCore env n || isAuxRecursor env n || isNoConfusion env n
        || lastComponentInternal n || isAuxByName n then
      some n.getPrefix
    else if let some info := env.getProjectionFnInfo? n then
      match env.find? info.ctorName with
      | some (.ctorInfo c) => some c.induct
      | _ => none
    else if isGeneratedLemmaSuffix n && isDefn env n.getPrefix then
      some n.getPrefix
    else
      none

/-- Follow `auxParent?` until a user-facing declaration is reached. -/
partial def ticketUnit (env : Environment) (n : Name) : Name :=
  match auxParent? env n with
  | some p => if p != n && env.contains p then ticketUnit env p else n
  | none => n

/-- Module that defines `n`, if it is imported. -/
def moduleOf? (env : Environment) (n : Name) : Option Name := do
  let idx ← env.getModuleIdxFor? n
  env.allImportedModuleNames[idx.toNat]?

/-- A declaration is *hardened* (set `H` in concept §2.2) if its module lies
under one of the given root prefixes, e.g. `Mathlib` or `Init`. -/
def isHardened (env : Environment) (prefixes : Array Name) (n : Name) : Bool :=
  match moduleOf? env n with
  | some m => prefixes.contains m.getRoot
  | none => false

end DpcAnalyzer
