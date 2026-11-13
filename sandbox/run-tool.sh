#!/bin/sh
# Runs one of the analyzer tools inside the sandbox with the toolchain's core
# library and runtime on the search path:
#   run-tool.sh <dpc-analyze|dpc-mutate|dpc-evidence|dpc-replay> <args...>
#   run-tool.sh lean-compile <root dir> <file.lean> <out.olean>   (evidence, SR-10)
set -eu
program="$1"
shift
LEAN_SYSROOT="$(lean --print-prefix)"
export LEAN_SYSROOT
export LD_LIBRARY_PATH="$LEAN_SYSROOT/lib/lean${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
# Lean loads a module from the first search path entry containing its root
# name. The toolchain's library comes first, so that no directory written by a
# build can shadow `Init`, `Std` or `Lean` (docs/adr/0009).
export LEAN_PATH="$LEAN_SYSROOT/lib/lean${LEAN_PATH:+:$LEAN_PATH}"
case "$program" in
  dpc-analyze|dpc-mutate|dpc-evidence|dpc-replay)
    exec "/opt/dpc/analyzer/.lake/build/bin/$program" "$@" ;;
  lean-compile)
    exec lean --root="$1" "$2" -o "$3" ;;
  *)
    echo "unknown tool: $program" >&2
    exit 2 ;;
esac
