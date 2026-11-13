import Lean
import DpcAnalyzer.Mutate

/-!
How a reviewer sees a declaration: its components (type, definition body,
constructors), pretty-printed with binder types, each with a glossary of the
constants it uses (SR-21). Shared by `dpc-mutate --render` (with the
submission's environment extensions) and `dpc-render` (with trusted extensions
only, docs/adr/0011), so that both render with exactly the same settings.
-/

open Lean Meta DpcAnalyzer.Mutate

namespace DpcAnalyzer.Render

/-- Binder types are always shown, otherwise a change hidden in a type
(ℝ³ → ℝ⁴) would be invisible. -/
def pp (e : Expr) : MetaM String :=
  withOptions (fun o => o.setBool `pp.funBinderTypes true |>.setBool `pp.piBinderTypes true) do
    return toString (← ppExpr e)

/-- The constants a component mentions, with their types. The declaration
itself, internal names and instances are left out; sorted by name, so the
output is deterministic. -/
def glossary (e : Expr) (self : Name) : MetaM Json := do
  let env ← getEnv
  let names := e.getUsedConstants.qsort (fun a b => a.toString < b.toString)
  let mut out := #[]
  for c in names do
    if c == self || c.isInternal then continue
    if ← isInstance c then continue
    let some ci := env.find? c | continue
    out := out.push <| Json.mkObj [("name", toJson (toString c)), ("type", toJson (← pp ci.type))]
  return Json.arr out

/-- The components of a declaration: `(target, label, expression)`. `lookup`
finds the constructors of an inductive type. -/
def components (lookup : Name → Option ConstantInfo) (ci : ConstantInfo) :
    Array (Target × String × Expr) := Id.run do
  let mut out := #[(Target.type, "", ci.type)]
  match ci with
  | .defnInfo v => out := out.push (.value, "", v.value)
  | .inductInfo v =>
    for c in v.ctors do
      if let some cinfo := lookup c then
        out := out.push (.ctor, toString c, cinfo.type)
  | _ => pure ()
  return out

def componentJson (target : Target) (label : String) (e : Expr) (self : Name) : MetaM Json :=
  return Json.mkObj [("target", toJson target.toString), ("label", toJson label),
                     ("text", toJson (← pp e)), ("glossary", ← glossary e self)]

end DpcAnalyzer.Render
