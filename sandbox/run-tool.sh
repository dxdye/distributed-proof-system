#!/bin/sh
# Runs one of the analyzer tools (dpc-analyze, dpc-mutate) inside the sandbox
# with the toolchain's core library and runtime on the search path:
#   run-tool.sh <program> <args...>
set -eu
program="$1"
shift
case "$program" in
  dpc-analyze|dpc-mutate) ;;
  *) echo "unknown tool: $program" >&2; exit 2 ;;
esac
LEAN_SYSROOT="$(lean --print-prefix)"
export LEAN_SYSROOT
export LD_LIBRARY_PATH="$LEAN_SYSROOT/lib/lean${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "/opt/dpc/analyzer/.lake/build/bin/$program" "$@"
