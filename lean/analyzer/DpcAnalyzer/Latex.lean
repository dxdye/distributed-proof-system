import Lean

/-!
Mechanical LaTeX typesetting of a closed Lean term (docs/adr/0012).

Not a translation: the same term, written as a formula. Every construct has
exactly one rendering, and whatever has none (let, match, projections, open
terms) makes the whole term untypeset, so that nothing is shown that the term
does not say. What matters for junk values stays visible:

* subtraction, division and remainder on `ℕ` and `ℤ` carry the type as a
  subscript (`a -_ℕ b` is truncated subtraction, `a /_ℕ b` floor division);
* casts are written `(n : ℝ)`;
* binders keep their types; implicit and instance arguments are left out.

The Lean text stays the binding version; the client says so.
-/

open Lean Meta

namespace DpcAnalyzer.Latex

/-- How tightly a fragment binds (larger: tighter). -/
abbrev Prec := Nat
def pBinder : Prec := 0
def pImp : Prec := 1
def pOr : Prec := 2
def pAnd : Prec := 3
def pNot : Prec := 4
def pRel : Prec := 5
def pAdd : Prec := 6
def pMul : Prec := 7
def pNeg : Prec := 8
def pPow : Prec := 9
def pApp : Prec := 10
def pAtom : Prec := 11

structure Frag where
  tex : String
  prec : Prec

def Frag.at (f : Frag) (p : Prec) : String :=
  if f.prec < p then s!"\\left({f.tex}\\right)" else f.tex

def atom (s : String) : Frag := ⟨s, pAtom⟩

def unsupported {α} (what : String) : MetaM α :=
  throwError "no unambiguous typesetting for {what}"

/-! ## Names -/

def greek : List (Char × String) := [
  ('α', "\\alpha"), ('β', "\\beta"), ('γ', "\\gamma"), ('δ', "\\delta"),
  ('ε', "\\varepsilon"), ('ζ', "\\zeta"), ('η', "\\eta"), ('θ', "\\theta"),
  ('ι', "\\iota"), ('κ', "\\kappa"), ('λ', "\\lambda"), ('μ', "\\mu"), ('ν', "\\nu"),
  ('ξ', "\\xi"), ('π', "\\pi"), ('ρ', "\\rho"), ('σ', "\\sigma"), ('τ', "\\tau"),
  ('φ', "\\varphi"), ('χ', "\\chi"), ('ψ', "\\psi"), ('ω', "\\omega"),
  ('Γ', "\\Gamma"), ('Δ', "\\Delta"), ('Θ', "\\Theta"), ('Λ', "\\Lambda"),
  ('Π', "\\Pi"), ('Σ', "\\Sigma"), ('Φ', "\\Phi"), ('Ψ', "\\Psi"), ('Ω', "\\Omega")]

def escapeText (s : String) : String :=
  s.foldl (fun acc c => acc ++ match c with
    | '_' => "\\_" | '#' => "\\#" | '%' => "\\%" | '&' => "\\&" | '$' => "\\$"
    | '{' => "\\{" | '}' => "\\}" | '\\' => "\\backslash{}" | '^' => "\\hat{}" | '~' => "\\sim{}"
    | c => c.toString) ""

/-- A bound variable: Greek letters as commands, `₀…₉` and `_k` as subscripts,
longer names upright-italic. -/
def varName (n : Name) : String := Id.run do
  let s := (n.eraseMacroScopes).toString (escape := false)
  let mut base := ""
  let mut sub := ""
  let mut inSub := false
  let mut letters := 0
  for c in s.toList do
    if '₀' ≤ c && c ≤ '₉' then
      sub := sub.push (Char.ofNat ('0'.toNat + (c.toNat - '₀'.toNat)))
    else if c == '_' && !base.isEmpty then
      inSub := true
    else if inSub then
      sub := sub.push c
    else if let some (_, cmd) := greek.find? (·.1 == c) then
      base := base ++ cmd ++ "{}"
      letters := letters + 1
    else if c.isAlphanum || c == '\'' then
      base := base.push c
      letters := letters + 1
    else
      base := base ++ escapeText c.toString
  let shown := if letters > 1 && !base.contains '\\' then s!"\\mathit\{{base}}" else base
  return if sub.isEmpty then shown else s!"{shown}_\{{escapeText sub}}"

/-- A constant: its last two name components, upright. -/
def constName (n : Name) : String :=
  let parts := n.components.map (·.toString (escape := false))
  let short := match parts.reverse with
    | a :: b :: _ => s!"{b}.{a}"
    | [a] => a
    | [] => n.toString
  s!"\\operatorname\{{escapeText short}}"

/-! ## Types that read as sets of numbers -/

def numberSet? (e : Expr) : Option String :=
  match e.constName? with
  | some ``Nat => some "\\mathbb{N}"
  | some ``Int => some "\\mathbb{Z}"
  | some `Rat => some "\\mathbb{Q}"
  | some `Real => some "\\mathbb{R}"
  | some `Complex => some "\\mathbb{C}"
  | some `NNReal => some "\\mathbb{R}_{\\ge 0}"
  | _ => none

/-- Operator with the type written as a subscript where it changes the
meaning (truncated subtraction, floor division on ℕ and ℤ). -/
def typedOp (op : String) (ty : Expr) : String :=
  match ty.constName? with
  | some ``Nat => s!"\\mathbin\{{op}_\{\\mathbb\{N}}}"
  | some ``Int => s!"\\mathbin\{{op}_\{\\mathbb\{Z}}}"
  | _ => s!"\\mathbin\{{op}}"

/-! ## The translation -/

/-- Introduce a binder with a fresh, readable name. -/
def withBinder {α} (n : Name) (bi : BinderInfo) (t : Expr) (k : Expr → String → MetaM α) :
    MetaM α := do
  let lctx ← getLCtx
  let mut name := n.eraseMacroScopes
  if name.isAnonymous then name := `x
  while (lctx.findFromUserName? name).isSome do
    name := name.appendAfter "'"
  withLocalDecl name bi t fun x => k x (varName name)

mutual

partial def typeAnn (t : Expr) : MetaM String := do
  if let some s := numberSet? t then return s!"\\in {s}"
  return s!": {(← go t).at pImp}"

partial def binop (op : String) (p : Prec) (a b : Expr) : MetaM Frag := do
  return ⟨s!"{(← go a).at (p + 1)} {op} {(← go b).at (p + 1)}", p⟩

partial def call (head : String) (args : Array Expr) : MetaM Frag := do
  if args.isEmpty then return atom head
  let parts ← args.mapM fun a => return (← go a).at pBinder
  return ⟨s!"{head}\\left({", ".intercalate parts.toList}\\right)", pApp⟩

/-- Explicit arguments of an application, by the binder kinds of the head. -/
partial def explicitArgs (f : Expr) (args : Array Expr) : MetaM (Array Expr) := do
  let info ← getFunInfoNArgs f args.size
  let mut out := #[]
  for h : i in [0:args.size] do
    let explicit := match info.paramInfo[i]? with
      | some p => p.binderInfo.isExplicit
      | none => true
    if explicit then out := out.push args[i]
  return out

partial def bigOp (sym : String) (index : Expr) (f : Expr) : MetaM Frag := do
  match f with
  | .lam n t b bi =>
    withBinder n bi t fun x name => do
      let body ← go (b.instantiate1 x)
      let range ← if index.isAppOf `Finset.univ then pure name
        else pure s!"{name} \\in {(← go index).at pRel}"
      return ⟨s!"{sym}_\{{range}} {body.at pMul}", pAdd⟩
  | _ => unsupported "a big operator without a bound variable"

partial def known (c : Name) (f : Expr) (args : Array Expr) : MetaM (Option Frag) := do
  let n := args.size
  let arg (i : Nat) : Expr := args[i]!
  match c, n with
  -- logic
  | ``And, 2 => return some ⟨s!"{(← go (arg 0)).at (pAnd + 1)} \\land {(← go (arg 1)).at pAnd}", pAnd⟩
  | ``Or, 2 => return some ⟨s!"{(← go (arg 0)).at (pOr + 1)} \\lor {(← go (arg 1)).at pOr}", pOr⟩
  | ``Not, 1 => return some ⟨s!"\\neg {(← go (arg 0)).at pNot}", pNot⟩
  | ``Iff, 2 => return some ⟨s!"{(← go (arg 0)).at (pImp + 1)} \\iff {(← go (arg 1)).at (pImp + 1)}", pImp⟩
  | ``True, 0 => return some (atom "\\mathrm{True}")
  | ``False, 0 => return some (atom "\\mathrm{False}")
  | ``Exists, 2 =>
    match arg 1 with
    | .lam bn t b bi =>
      withBinder bn bi t fun x name => do
        let body ← go (b.instantiate1 x)
        return some ⟨s!"\\exists {name} {← typeAnn t},\\ {body.at pBinder}", pBinder⟩
    | _ => return none
  -- relations
  | ``Eq, 3 => return some (← binop "=" pRel (arg 1) (arg 2))
  | ``Ne, 3 => return some (← binop "\\neq" pRel (arg 1) (arg 2))
  | ``LT.lt, 4 => return some (← binop "<" pRel (arg 2) (arg 3))
  | ``LE.le, 4 => return some (← binop "\\le" pRel (arg 2) (arg 3))
  | ``GT.gt, 4 => return some (← binop ">" pRel (arg 2) (arg 3))
  | ``GE.ge, 4 => return some (← binop "\\ge" pRel (arg 2) (arg 3))
  | ``Membership.mem, 5 => return some (← binop "\\in" pRel (arg 4) (arg 3))
  | ``HasSubset.Subset, 4 => return some (← binop "\\subseteq" pRel (arg 2) (arg 3))
  -- arithmetic
  | ``HAdd.hAdd, 6 => return some (← binop "+" pAdd (arg 4) (arg 5))
  | ``HSub.hSub, 6 => return some (← binop (typedOp "-" (arg 0)) pAdd (arg 4) (arg 5))
  | ``HMul.hMul, 6 => return some (← binop "\\cdot" pMul (arg 4) (arg 5))
  | ``HSMul.hSMul, 6 => return some (← binop "\\cdot" pMul (arg 4) (arg 5))
  | ``HDiv.hDiv, 6 =>
    match (arg 0).constName? with
    | some ``Nat | some ``Int => return some (← binop (typedOp "/" (arg 0)) pMul (arg 4) (arg 5))
    | _ => return some ⟨s!"\\frac\{{(← go (arg 4)).tex}}\{{(← go (arg 5)).tex}}", pApp⟩
  | ``HMod.hMod, 6 => return some (← binop (typedOp "\\bmod" (arg 0)) pMul (arg 4) (arg 5))
  | ``HPow.hPow, 6 => return some ⟨s!"{(← go (arg 4)).at (pPow + 1)}^\{{(← go (arg 5)).tex}}", pPow⟩
  | ``Neg.neg, 3 => return some ⟨s!"-{(← go (arg 2)).at pNeg}", pNeg⟩
  | ``Inv.inv, 3 => return some ⟨s!"{(← go (arg 2)).at (pPow + 1)}^\{-1}", pPow⟩
  | ``OfNat.ofNat, 3 =>
    match arg 1 with
    | .lit (.natVal v) => return some (atom (toString v))
    | _ => return none
  | `abs, 4 => return some (atom s!"\\left|{(← go (arg 3)).tex}\\right|")
  | `Norm.norm, 3 => return some (atom s!"\\left\\lVert {(← go (arg 2)).tex}\\right\\rVert")
  -- bundled maps used as functions, order extremes, coercions into `WithTop`
  | `DFunLike.coe, k =>
    if k < 5 then return none
    let head ← go (arg 4)
    let rest := args.extract 5 k
    if rest.isEmpty then return some head
    return some (← call (head.at pApp) rest)
  | `Top.top, 2 => return some (atom "\\top")
  | `Bot.bot, 2 => return some (atom "\\bot")
  | `WithTop.some, 2 => return some ⟨s!"\{\\uparrow}{(← go (arg 1)).at pApp}", pApp⟩
  -- casts: written with their target type
  | ``Nat.cast, 3 | ``Int.cast, 3 | `Rat.cast, 3 =>
    return some (atom s!"\\left({(← go (arg 2)).tex} : {(← go (← inferType (mkAppN f args))).tex}\\right)")
  | `Complex.ofReal, 1 => return some (atom s!"\\left({(← go (arg 0)).tex} : \\mathbb\{C}\\right)")
  -- sets
  | `Set.univ, 1 => return some (atom "\\mathrm{univ}")
  | ``EmptyCollection.emptyCollection, 2 => return some (atom "\\emptyset")
  | ``Union.union, 4 => return some (← binop "\\cup" pAdd (arg 2) (arg 3))
  | ``Inter.inter, 4 => return some (← binop "\\cap" pMul (arg 2) (arg 3))
  | ``SDiff.sdiff, 4 => return some (← binop "\\setminus" pAdd (arg 2) (arg 3))
  | `SProd.sprod, 6 => return some (← binop "\\times" pMul (arg 4) (arg 5))
  | `Set.Icc, 4 => return some (atom s!"\\left[{(← go (arg 2)).tex}, {(← go (arg 3)).tex}\\right]")
  | `Set.Ico, 4 => return some (atom s!"\\left[{(← go (arg 2)).tex}, {(← go (arg 3)).tex}\\right)")
  | `Set.Ioc, 4 => return some (atom s!"\\left({(← go (arg 2)).tex}, {(← go (arg 3)).tex}\\right]")
  | `Set.Ioo, 4 => return some (atom s!"\\left({(← go (arg 2)).tex}, {(← go (arg 3)).tex}\\right)")
  | `Set.Ici, 3 => return some (atom s!"\\left[{(← go (arg 2)).tex}, \\infty\\right)")
  | `Set.Ioi, 3 => return some (atom s!"\\left({(← go (arg 2)).tex}, \\infty\\right)")
  | `Set.Iic, 3 => return some (atom s!"\\left(-\\infty, {(← go (arg 2)).tex}\\right]")
  | `Set.Iio, 3 => return some (atom s!"\\left(-\\infty, {(← go (arg 2)).tex}\\right)")
  | `setOf, 2 =>
    match arg 1 with
    | .lam bn t b bi =>
      withBinder bn bi t fun x name => do
        let body ← go (b.instantiate1 x)
        return some (atom s!"\\left\\\{{name} {← typeAnn t} \\mid {body.tex}\\right\\}")
    | _ => return none
  -- analysis and number theory
  | `Real.sqrt, 1 => return some ⟨s!"\\sqrt\{{(← go (arg 0)).tex}}", pApp⟩
  | `Real.exp, 1 | `Complex.exp, 1 => return some (← call "\\exp" #[arg 0])
  | `Real.log, 1 | `Complex.log, 1 => return some (← call "\\log" #[arg 0])
  | `Real.sin, 1 => return some (← call "\\sin" #[arg 0])
  | `Real.cos, 1 => return some (← call "\\cos" #[arg 0])
  | `Real.pi, 0 => return some (atom "\\pi")
  | `Complex.I, 0 => return some (atom "i")
  | `Complex.re, 1 => return some (← call "\\operatorname{Re}" #[arg 0])
  | `Complex.im, 1 => return some (← call "\\operatorname{Im}" #[arg 0])
  | `riemannZeta, 1 => return some (← call "\\zeta" #[arg 0])
  | `Finset.sum, 5 => return some (← bigOp "\\sum" (arg 3) (arg 4))
  | `Finset.prod, 5 => return some (← bigOp "\\prod" (arg 3) (arg 4))
  -- types
  | ``Nat, 0 | ``Int, 0 | `Rat, 0 | `Real, 0 | `Complex, 0 | `NNReal, 0 =>
    return (numberSet? f).map atom
  | `Fin, 1 => return some ⟨s!"\\mathrm\{Fin}\\,{(← go (arg 0)).at pApp}", pApp⟩
  | `EuclideanSpace, 2 =>
    match (arg 1).getAppFn.constName?, (arg 1).getAppArgs with
    | some `Fin, #[k] => return some ⟨s!"{(← go (arg 0)).at pAtom}^\{{(← go k).tex}}", pPow⟩
    | _, _ => return none
  | ``Prod, 2 => return some (← binop "\\times" pMul (arg 0) (arg 1))
  | _, _ => return none

partial def app (e : Expr) : MetaM Frag := do
  let f := e.getAppFn
  let args := e.getAppArgs
  match f with
  | .const c _ =>
    if let some frag ← known c f args then return frag
    call (constName c) (← explicitArgs f args)
  | .fvar _ => call (← go f).tex args
  | _ => unsupported "an application of a complex head"

partial def go (e : Expr) : MetaM Frag := do
  match e with
  | .mdata _ b => go b
  | .fvar id => return atom (varName (← id.getDecl).userName)
  | .lit (.natVal v) => return atom (toString v)
  | .lit (.strVal s) => return atom s!"\\text\{``{escapeText s}''}"
  | .sort l => return atom (if l.isZero then "\\mathrm{Prop}" else "\\mathrm{Type}")
  | .forallE n t b bi =>
    if !b.hasLooseBVars then
      let arrow := if ← isProp t then "\\implies" else "\\to"
      let a ← go t
      let r ← withLocalDecl n bi t fun x => go (b.instantiate1 x)
      return ⟨s!"{a.at (pImp + 1)} {arrow} {r.at pImp}", pImp⟩
    else if ← isProp e then
      withBinder n bi t fun x name => do
        let body ← go (b.instantiate1 x)
        return ⟨s!"\\forall {name} {← typeAnn t},\\ {body.at pBinder}", pBinder⟩
    else
      withBinder n bi t fun x name => do
        let body ← go (b.instantiate1 x)
        return ⟨s!"\\left({name} : {(← go t).at pImp}\\right) \\to {body.at pImp}", pImp⟩
  | .lam n t b bi =>
    withBinder n bi t fun x name => do
      let body ← go (b.instantiate1 x)
      return ⟨s!"\\left({name} : {(← go t).at pImp}\\right) \\mapsto {body.at pBinder}", pBinder⟩
  | .const .. | .app .. => app e
  | .letE .. => unsupported "let"
  | .proj .. => unsupported "a projection"
  | .bvar _ | .mvar _ => unsupported "an open term"

end

/-- Longest LaTeX shown; longer terms are left to the Lean text. -/
def maxChars : Nat := 6000

/-- The term as LaTeX, or `none` if some part has no unambiguous rendering. -/
def typeset (e : Expr) : MetaM (Option String) := do
  try
    let frag ← go (← instantiateMVars e)
    return if frag.tex.length ≤ maxChars then some frag.tex else none
  catch _ =>
    return none

end DpcAnalyzer.Latex
