/-!
Red-team fixture (verification §11.2, SR-20).

Code that runs at build time (here: `#eval`) tries to write into the source
tree and to reach the network. Inside the sandbox both must fail; the build
itself still succeeds and reports the outcome as messages.

Never build this on a host outside the sandbox.
-/

def tryWrite (path : System.FilePath) (tag : String) : IO String := do
  try
    IO.FS.writeFile path "pwned"
    return s!"{tag}:OK"
  catch _ =>
    return s!"{tag}:FAILED"

def tryNetwork : IO String := do
  try
    let out ← IO.Process.output
      { cmd := "curl", args := #["-sS", "--max-time", "5", "https://example.com"] }
    return if out.exitCode == 0 then "NET:OK" else "NET:FAILED"
  catch _ =>
    return "NET:FAILED"

#eval do
  IO.println (← tryWrite "PWNED.txt" "WRITE_SOURCE")
  IO.println (← tryWrite "/etc/pwned" "WRITE_SYSTEM")
  IO.println (← tryWrite ".lake/build/allowed.txt" "WRITE_BUILD")
  IO.println (← tryNetwork)

theorem redteam_root : True := trivial
