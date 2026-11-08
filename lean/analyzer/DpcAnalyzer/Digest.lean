import Lean
import DpcAnalyzer.Sha256

/-!
# Merkle content hash of expressions

`digest e` is the SHA-256 of a canonical encoding of `e`, computed bottom-up:
every node hashes its constructor tag and the digests of its children. A
cache of already hashed subterms keeps the cost linear in the size of the
expression *DAG* (expressions share subterms heavily; a naive serialisation
could grow exponentially).

The hash is invariant under α-renaming: binder names, binder info and
metadata are not part of the encoding, as they do not change the meaning.
-/

open Lean

namespace DpcAnalyzer.Digest

abbrev M := StateM (Std.HashMap Expr ByteArray)

private def tag (t : UInt8) : ByteArray := ByteArray.empty.push t

private def str (s : String) : ByteArray := s.toUTF8 ++ (ByteArray.empty.push 0)

private def nat (n : Nat) : ByteArray := str (toString n)

private def levels (ls : List Level) : ByteArray :=
  ls.foldl (fun acc l => acc ++ str (toString l)) ByteArray.empty

partial def digest (e : Expr) : M ByteArray := do
  if let some d := (← get).get? e then
    return d
  -- Note: `pure`, not `return`, inside the arms — `return` would leave `digest`.
  let enc : ByteArray ← match e with
    | .bvar i => pure (tag 1 ++ nat i)
    | .sort l => pure (tag 2 ++ str (toString l))
    | .const n ls => pure (tag 3 ++ str (toString n) ++ levels ls)
    | .app f a => do pure (tag 4 ++ (← digest f) ++ (← digest a))
    | .lam _ t b _ => do pure (tag 5 ++ (← digest t) ++ (← digest b))
    | .forallE _ t b _ => do pure (tag 6 ++ (← digest t) ++ (← digest b))
    | .letE _ t v b _ => do pure (tag 7 ++ (← digest t) ++ (← digest v) ++ (← digest b))
    | .lit (.natVal n) => pure (tag 8 ++ nat n)
    | .lit (.strVal s) => pure (tag 9 ++ str s)
    | .mdata _ inner => digest inner  -- metadata does not change meaning
    | .proj s i x => do pure (tag 10 ++ str (toString s) ++ nat i ++ (← digest x))
    | .fvar id => pure (tag 11 ++ str (toString id.name))
    | .mvar id => pure (tag 12 ++ str (toString id.name))
  let d := if e.isMData then enc else Sha256.hash enc
  modify (·.insert e d)
  return d

/-- Hex digest of one expression (fresh cache: memory stays bounded per call). -/
def hexDigest (e : Expr) : String :=
  Sha256.toHex ((digest e).run' {})

end DpcAnalyzer.Digest
