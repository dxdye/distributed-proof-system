import Lean

/-!
# Mutation generator and equivalence filter (concept §5.1; SR-06, SR-07)

Mutants are small, targeted changes of a declaration's statement (for theorems)
or body (for definitions). Operators:

* `relation` — `<` ↔ `≤`, `>` ↔ `≥` (instances are re-synthesised),
* `constant` — numeric literal `k` → `k + 1`, `k − 1`,
* `interval` — `Set.Icc` ↔ `Set.Ico` ↔ `Set.Ioc` ↔ `Set.Ioo`, `Set.Ici` ↔ `Set.Ioi`,
  `Set.Iic` ↔ `Set.Iio` (only if the constants exist, i.e. with Mathlib),
* `drop_hypothesis` — remove a hypothesis that nothing else depends on,
* `swap_quantifiers` — `∀ x, ∃ y, P` → `∃ y, ∀ x, P`.

Every mutant must type-check (SR-07). The **equivalence filter is local**: it
tries to prove that the changed part means the same *at the place of the
change*, in the context of all enclosing variables and hypotheses —
`a ↔ a'` for propositions, `t = t'` for terms, derivability of a dropped
hypothesis from the others. (Comparing whole statements, `M ↔ D`, would be
wrong for proven theorems: `D` is true, so `M ↔ D` holds for every true
mutant, including faithful-looking but different claims that make good
honeypots; see docs/adr/0007.) A mutant whose change is provably equivalent is
discarded, so a reviewer who judges correctly is never penalised.
-/

open Lean Meta Elab

namespace DpcAnalyzer.Mutate

/-- Where a mutation was applied. -/
inductive Target where
  | type
  | value
  | ctor  -- constructor of an inductive type / structure (its fields carry the meaning)
  deriving BEq

def Target.toString : Target → String
  | .type => "type"
  | .value => "value"
  | .ctor => "ctor"

/-- One applied mutation. `goal` is the closed proposition whose proof shows
that the change preserves meaning. -/
structure Mutation where
  operator : String
  detail : String
  result : Expr
  goal : Expr

/-- Relation swaps; arguments `(α, inst, a, b)`. -/
def relationSwaps : List (Name × Name) :=
  [(``LT.lt, ``LE.le), (``LE.le, ``LT.lt), (``GT.gt, ``GE.ge), (``GE.ge, ``GT.gt)]

/-- Interval constants with identical signatures that may be swapped directly. -/
def intervalSwaps : List (Name × Name) :=
  [(`Set.Icc, `Set.Ioo), (`Set.Ioo, `Set.Icc), (`Set.Icc, `Set.Ico), (`Set.Ico, `Set.Icc),
   (`Set.Icc, `Set.Ioc), (`Set.Ioc, `Set.Icc), (`Set.Ici, `Set.Ioi), (`Set.Ioi, `Set.Ici),
   (`Set.Iic, `Set.Iio), (`Set.Iio, `Set.Iic)]

/-- Close `body` over the current local context (all enclosing binders). -/
def closeOverContext (body : Expr) : MetaM Expr := do
  let fvars := (← getLCtx).getFVars
  mkForallFVars fvars body

/-- Candidate replacements of a single subterm `e`, with their equivalence goals. -/
def rewritesAt (env : Environment) (e : Expr) : MetaM (Array (String × String × Expr × Expr)) := do
  let mut out := #[]
  -- relation
  for (src, dst) in relationSwaps do
    if e.isAppOfArity src 4 then
      let args := e.getAppArgs
      try
        let e' ← mkAppM dst #[args[2]!, args[3]!]
        out := out.push ("relation", s!"{src} → {dst}", e', mkApp2 (mkConst ``Iff) e e')
      catch _ => pure ()
  -- constant
  if e.isAppOfArity ``OfNat.ofNat 3 then
    if let .lit (.natVal k) := e.getArg! 1 then
      let ty := e.getArg! 0
      for k' in (if k == 0 then [k + 1] else [k + 1, k - 1]) do
        try
          let e' ← mkNumeral ty k'
          out := out.push ("constant", s!"{k} → {k'}", e', ← mkEq e e')
        catch _ => pure ()
  -- interval
  for (src, dst) in intervalSwaps do
    if e.isAppOf src && env.contains dst then
      let e' := mkAppN (.const dst e.getAppFn.constLevels!) e.getAppArgs
      try
        out := out.push ("interval", s!"{src} → {dst}", e', ← mkEq e e')
      catch _ => pure ()
  return out

/-- All single-site mutations of `root`. The `n`-th matching site is rewritten
in pass `n`; the visitor runs inside the binders, so the local context holds
every enclosing variable and hypothesis. -/
partial def siteMutations (env : Environment) (root : Expr) (maxSites : Nat) :
    MetaM (Array Mutation) := do
  let mut result := #[]
  let mut site := 0
  repeat
    if site ≥ maxSites then break
    let counter ← IO.mkRef 0
    let found ← IO.mkRef (none : Option (String × String × Expr))
    let target := site
    let mutated ← Meta.transform root (post := fun e => do
      let rewrites ← rewritesAt env e
      let mut chosen : Option Expr := none
      for (op, detail, e', goal) in rewrites do
        let n ← counter.get
        counter.set (n + 1)
        if n == target && chosen.isNone then
          found.set (some (op, detail, ← closeOverContext goal))
          chosen := some e'
      match chosen with
      | some e' => return .done e'
      | none => return .continue)
    match ← found.get with
    | some (op, detail, goal) =>
      result := result.push { operator := op, detail, result := mutated, goal }
      site := site + 1
    | none => break
  return result

/-- `drop_hypothesis` and `swap_quantifiers` work on the outer ∀-telescope. -/
def telescopeMutations (type : Expr) : MetaM (Array Mutation) :=
  forallTelescope type fun xs body => do
    let mut out := #[]
    -- drop a hypothesis nothing depends on
    for i in [0:xs.size] do
      let x := xs[i]!
      let xType ← inferType x
      unless ← isProp xType do continue
      let rest := xs.extract (i + 1) xs.size
      let usedLater ← rest.anyM fun y => return (← inferType y).containsFVar x.fvarId!
      if usedLater || body.containsFVar x.fvarId! then continue
      let others := xs.eraseIdx! i
      let mutated ← mkForallFVars others body
      -- equivalent iff the hypothesis follows from the other binders
      let goal ← mkForallFVars (xs.extract 0 i) xType
      out := out.push { operator := "drop_hypothesis", detail := s!"binder {i}",
                        result := mutated, goal }
    -- ∀ x, ∃ y, P  →  ∃ y, ∀ x, P   (x = last binder, type of y independent of x)
    if h : xs.size > 0 then
      let x := xs[xs.size - 1]
      if body.isAppOfArity ``Exists 2 && !(← isProp (← inferType x)) then
        let α := body.getArg! 0
        let lam := body.getArg! 1
        if !α.containsFVar x.fvarId! && lam.isLambda then
          let swapped ← withLocalDeclD lam.bindingName! α fun y => do
            let p := lam.beta #[y]
            let inner ← mkForallFVars #[x] p
            mkAppM ``Exists #[← mkLambdaFVars #[y] inner]
          let outer := xs.pop
          let original ← mkForallFVars #[x] body
          let goal ← mkForallFVars outer (mkApp2 (mkConst ``Iff) original swapped)
          out := out.push { operator := "swap_quantifiers", detail := "∀∃ → ∃∀",
                            result := ← mkForallFVars outer swapped, goal }
    return out

/-- Does `e` type-check (and keep its sort/type)? -/
def typeChecks (e : Expr) (expected? : Option Expr) : MetaM Bool := do
  try
    Meta.check e
    if let some expected := expected? then
      return ← isDefEq (← inferType e) expected
    return true
  catch _ => return false

/-- Try to close `goal` with any of the tactic scripts within a heartbeat budget.
Returns the script that succeeded. -/
def proveWith (goal : Expr) (scripts : Array String) (heartbeats : Nat) :
    TermElabM (Option String) := do
  let env ← getEnv
  for script in scripts do
    -- A script may be a sequence (`intros; omega`); parenthesised it is one tactic.
    let stx ← match Parser.runParserCategory env `tactic s!"({script})" with
      | .ok stx => pure stx
      | .error err => throwError "cannot parse tactic script `{script}`: {err}"
    let saved ← saveState
    -- Elaboration normally recovers from errors by inserting `sorry`; a goal
    -- "closed" that way is not proven. Disable recovery and double-check.
    let ok ← try
        withCurrHeartbeats <| withTheReader Core.Context
            (fun ctx => { ctx with maxHeartbeats := heartbeats * 1000 }) <|
          Term.withoutErrToSorry do
            let hadErrors := (← Core.getMessageLog).hasErrors
            let mvar ← mkFreshExprMVar goal
            let remaining ← Tactic.run mvar.mvarId! (Tactic.evalTactic stx)
            Term.synthesizeSyntheticMVarsNoPostponing
            let proof ← instantiateMVars mvar
            let hasErrors := (← Core.getMessageLog).hasErrors
            pure (remaining.isEmpty && !proof.hasExprMVar && !proof.hasSorry
                  && (hadErrors || !hasErrors))
      catch _ => pure false
    saved.restore
    if ok then return some script
  return none

/-! ## Component-level equivalence (definitions and structure fields)

For a proven theorem only the local check is meaningful (ADR 0007). Definition
bodies and structure fields are not truths, so equivalence of the *whole*
component is meaningful there and catches changes compensated elsewhere, e.g.
`0 < n ∧ 1 ≤ n` → `0 ≤ n ∧ 1 ≤ n`. -/

/-- `∀ xs, body ↔ body'` (or `=` for non-propositions) for two definition bodies
with the same λ-telescope. -/
def valueGoal (original mutant : Expr) : MetaM (Option Expr) :=
  lambdaTelescope original fun xs body => do
    let body' := mutant.beta xs
    if body'.isLambda then return none  -- telescopes do not line up
    try
      if ← isProp body then
        return some (← mkForallFVars xs (mkApp2 (mkConst ``Iff) body body'))
      return some (← mkForallFVars xs (← mkEq body body'))
    catch _ => return none

/-- `∀ earlier binders, field ↔ field'` for the first ∀-binder (constructor field)
whose type differs between `original` and `mutant`. -/
partial def fieldGoal (original mutant : Expr) (fvars : Array Expr := #[]) :
    MetaM (Option Expr) := do
  match original, mutant with
  | .forallE n t b bi, .forallE _ t' b' _ =>
    let ti := t.instantiateRev fvars
    let ti' := t'.instantiateRev fvars
    if ti == ti' then
      withLocalDecl n bi ti fun x => fieldGoal b b' (fvars.push x)
    else if ← isProp ti then
      return some (← mkForallFVars fvars (mkApp2 (mkConst ``Iff) ti ti'))
    else
      return none
  | _, _ => return none

/-! ## Automatic detection (the checks of concept §5.2)

A mutant that an automatic check already flags measures the checker, not the
reviewer. Same checks as the machine-checked refutations of concept §5.2:
* vacuity — `False` follows from the hypotheses (or structure fields),
* triviality — the statement is proven by trivial tactics. -/

def vacuityScripts : Array String :=
  #["intros; omega", "intros; simp_all", "intros; contradiction", "intros; decide"]

def trivialityScripts : Array String :=
  #["intros; trivial", "intros; rfl", "intros; decide", "intros; omega", "intros; simp"]

/-- `∀ xs, False` over the ∀-telescope of `t`, if it has a propositional binder. -/
def vacuityGoal (t : Expr) : MetaM (Option Expr) :=
  forallTelescope t fun xs _ => do
    let hasHyp ← xs.anyM fun x => do isProp (← inferType x)
    if !hasHyp then return none
    return some (← mkForallFVars xs (mkConst ``False))

/-- Result of the automatic checks on one statement. -/
structure Lints where
  vacuous : Bool
  trivial : Bool

def lints (t : Expr) (isTheorem : Bool) (heartbeats : Nat) : TermElabM Lints := do
  let vacuous ← match ← vacuityGoal t with
    | some g => pure (← proveWith g vacuityScripts heartbeats).isSome
    | none => pure false
  let trivial ← if isTheorem && (← isProp t) then
      pure (← proveWith t trivialityScripts heartbeats).isSome
    else pure false
  return { vacuous, trivial }

/-- Which check flags the mutant but not the original (the honeypot would then
measure the checker). -/
def autoDetected (original mutant : Lints) : Option String :=
  if mutant.vacuous && !original.vacuous then some "vacuous"
  else if mutant.trivial && !original.trivial then some "trivial"
  else none

end DpcAnalyzer.Mutate
