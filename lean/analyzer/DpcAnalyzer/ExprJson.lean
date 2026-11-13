import Lean

/-!
JSON encoding of closed expressions (no free or meta variables).

`dpc-mutate` produces honeypots in a process that has loaded the submission's
environment extensions. `dpc-render` shows the same expressions with trusted
extensions only (docs/adr/0011) and must not load the submission's extensions.
The mutated expression therefore travels between the two processes as JSON.

The encoding is exact: binder names and kinds, `mdata`, literals and universe
levels are kept, so the second rendering differs only by the extensions.
`dpc-mutate` checks the round trip and leaves out mutants that do not survive
it. `mdata` holding syntax cannot be encoded.
-/

open Lean

namespace DpcAnalyzer.ExprJson

private def str (s : String) : Json := Json.str s

def nameToJson (n : Name) : Json :=
  let rec parts : Name → List Json → List Json
    | .anonymous, acc => acc
    | .str p s, acc => parts p (str s :: acc)
    | .num p k, acc => parts p (toJson k :: acc)
  Json.arr (parts n []).toArray

def nameOfJson (j : Json) : Except String Name := do
  let mut n := Name.anonymous
  for part in ← j.getArr? do
    match part with
    | .str s => n := .str n s
    | .num _ => n := .num n (← part.getNat?)
    | _ => throw "name: expected strings and numbers"
  return n

partial def levelToJson : Level → Except String Json
  | .zero => return Json.arr #[str "z"]
  | .succ l => return Json.arr #[str "s", ← levelToJson l]
  | .max a b => return Json.arr #[str "m", ← levelToJson a, ← levelToJson b]
  | .imax a b => return Json.arr #[str "i", ← levelToJson a, ← levelToJson b]
  | .param n => return Json.arr #[str "p", nameToJson n]
  | .mvar _ => throw "level metavariable"

partial def levelOfJson (j : Json) : Except String Level := do
  let a ← j.getArr?
  let some tag := a[0]? | throw "level: empty"
  match ← tag.getStr? with
  | "z" => return .zero
  | "s" => return .succ (← levelOfJson a[1]!)
  | "m" => return .max (← levelOfJson a[1]!) (← levelOfJson a[2]!)
  | "i" => return .imax (← levelOfJson a[1]!) (← levelOfJson a[2]!)
  | "p" => return .param (← nameOfJson a[1]!)
  | t => throw s!"level: unknown tag {t}"

def binderInfoCode : BinderInfo → String
  | .default => "d" | .implicit => "i" | .strictImplicit => "s" | .instImplicit => "I"

def binderInfoOf : String → Except String BinderInfo
  | "d" => return .default | "i" => return .implicit
  | "s" => return .strictImplicit | "I" => return .instImplicit
  | t => throw s!"binder info: unknown {t}"

def dataValueToJson : DataValue → Except String Json
  | .ofString v => return Json.arr #[str "s", str v]
  | .ofBool v => return Json.arr #[str "b", toJson v]
  | .ofName v => return Json.arr #[str "n", nameToJson v]
  | .ofNat v => return Json.arr #[str "N", str (toString v)]
  | .ofInt v => return Json.arr #[str "I", str (toString v)]
  | .ofSyntax _ => throw "mdata with syntax"

def dataValueOfJson (j : Json) : Except String DataValue := do
  let a ← j.getArr?
  match ← a[0]!.getStr? with
  | "s" => return .ofString (← a[1]!.getStr?)
  | "b" => return .ofBool (← a[1]!.getBool?)
  | "n" => return .ofName (← nameOfJson a[1]!)
  | "N" => match (← a[1]!.getStr?).toNat? with
    | some v => return .ofNat v
    | none => throw "mdata: bad nat"
  | "I" => match (← a[1]!.getStr?).toInt? with
    | some v => return .ofInt v
    | none => throw "mdata: bad int"
  | t => throw s!"mdata: unknown tag {t}"

partial def toJson' : Expr → Except String Json
  | .bvar i => return Json.arr #[str "b", toJson i]
  | .fvar _ => throw "free variable"
  | .mvar _ => throw "metavariable"
  | .sort l => return Json.arr #[str "S", ← levelToJson l]
  | .const n ls => return Json.arr #[str "c", nameToJson n, Json.arr (← ls.toArray.mapM levelToJson)]
  | .app f a => return Json.arr #[str "a", ← toJson' f, ← toJson' a]
  | .lam n t b bi =>
    return Json.arr #[str "l", nameToJson n, ← toJson' t, ← toJson' b, str (binderInfoCode bi)]
  | .forallE n t b bi =>
    return Json.arr #[str "f", nameToJson n, ← toJson' t, ← toJson' b, str (binderInfoCode bi)]
  | .letE n t v b nondep =>
    return Json.arr #[str "L", nameToJson n, ← toJson' t, ← toJson' v, ← toJson' b, toJson nondep]
  | .lit (.natVal v) => return Json.arr #[str "n", str (toString v)]
  | .lit (.strVal v) => return Json.arr #[str "t", str v]
  | .mdata m e => do
    let entries ← m.entries.toArray.mapM fun (k, v) => do
      return Json.arr #[nameToJson k, ← dataValueToJson v]
    return Json.arr #[str "m", Json.arr entries, ← toJson' e]
  | .proj s i e => return Json.arr #[str "j", nameToJson s, toJson i, ← toJson' e]

partial def ofJson' (j : Json) : Except String Expr := do
  let a ← j.getArr?
  let some tag := a[0]? | throw "expr: empty"
  match ← tag.getStr? with
  | "b" => return .bvar (← a[1]!.getNat?)
  | "S" => return .sort (← levelOfJson a[1]!)
  | "c" => return .const (← nameOfJson a[1]!) (← (← a[2]!.getArr?).mapM levelOfJson).toList
  | "a" => return .app (← ofJson' a[1]!) (← ofJson' a[2]!)
  | "l" => return .lam (← nameOfJson a[1]!) (← ofJson' a[2]!) (← ofJson' a[3]!)
                      (← binderInfoOf (← a[4]!.getStr?))
  | "f" => return .forallE (← nameOfJson a[1]!) (← ofJson' a[2]!) (← ofJson' a[3]!)
                          (← binderInfoOf (← a[4]!.getStr?))
  | "L" => return .letE (← nameOfJson a[1]!) (← ofJson' a[2]!) (← ofJson' a[3]!)
                       (← ofJson' a[4]!) (← a[5]!.getBool?)
  | "n" => match (← a[1]!.getStr?).toNat? with
    | some v => return .lit (.natVal v)
    | none => throw "expr: bad nat literal"
  | "t" => return .lit (.strVal (← a[1]!.getStr?))
  | "m" => do
    let entries ← (← a[1]!.getArr?).mapM fun entry => do
      let kv ← entry.getArr?
      return ((← nameOfJson kv[0]!), (← dataValueOfJson kv[1]!))
    return .mdata { entries := entries.toList } (← ofJson' a[2]!)
  | "j" => return .proj (← nameOfJson a[1]!) (← a[2]!.getNat?) (← ofJson' a[3]!)
  | t => throw s!"expr: unknown tag {t}"

/-- Encode, and check that decoding gives back exactly the same expression. -/
def encodeChecked (e : Expr) : Except String Json := do
  let j ← toJson' e
  let back ← ofJson' j
  unless back.equal e do
    throw "round trip changed the expression"
  unless (← toJson' back).compress == j.compress do
    throw "round trip changed the encoding"
  return j

end DpcAnalyzer.ExprJson
