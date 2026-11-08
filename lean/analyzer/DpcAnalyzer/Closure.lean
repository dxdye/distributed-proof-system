import Lean

/-!
# Trusted computing base and dependency closures (concept §2)

* `tcbEdges`: constants that determine the *meaning* of a declaration. Types
  always count; values only for definitions (proof irrelevance removes theorem
  bodies, and the kernel never unfolds `opaque` bodies); inductive types
  contribute their constructors.
* `allEdges`: every constant mentioned, proofs included — for `Dep(T)`.
-/

open Lean

namespace DpcAnalyzer

/-- Constants that determine the meaning of `ci` (concept §2.2). -/
def tcbEdges (ci : ConstantInfo) : Array Name :=
  let fromValue : Array Name := match ci with
    | .thmInfo _    => #[]
    | .opaqueInfo _ => #[]
    | .inductInfo v => v.ctors.toArray
    | .defnInfo v   => v.value.getUsedConstants
    | _             => #[]
  ci.type.getUsedConstants ++ fromValue

/-- All constants mentioned by `ci`, including proof terms (for `Dep(T)`). -/
def allEdges (ci : ConstantInfo) : Array Name :=
  let fromValue : Array Name := match ci with
    | .inductInfo v => v.ctors.toArray
    | _ => ((ci.value? (allowOpaque := true)).map Expr.getUsedConstants).getD #[]
  ci.type.getUsedConstants ++ fromValue

/-- Reachability from `roots` along `edges`. Nodes for which `expand` is false
are recorded but not expanded further. -/
partial def reach (env : Environment) (edges : ConstantInfo → Array Name)
    (expand : Name → Bool) (roots : List Name) : NameSet :=
  go roots {}
where
  go : List Name → NameSet → NameSet
    | [], acc => acc
    | n :: todo, acc =>
      if acc.contains n then go todo acc
      else
        let acc := acc.insert n
        if !expand n then go todo acc
        else match env.find? n with
          | none => go todo acc
          | some ci => go ((edges ci).toList ++ todo) acc

/-- `TCB(T)`: smallest set containing `T`, closed under `tcbEdges`. -/
def tcb (env : Environment) (root : Name) : NameSet :=
  reach env tcbEdges (fun _ => true) [root]

/-- The non-hardened part of `Dep(T)` plus its hardened frontier.

Hardened declarations are not expanded. This is exact for computing
`Dep(T) \ H`: a hardened library (Mathlib, core) cannot import the analysed
repository, so nothing reachable from `H` lies outside `H`. -/
def depNew (env : Environment) (hardened : Name → Bool) (root : Name) : NameSet :=
  reach env allEdges (fun n => !hardened n) [root]

end DpcAnalyzer
