#!/bin/sh
# Runs dpc-analyze inside the sandbox with the toolchain's core library and
# runtime on the search path. Arguments are passed through unchanged.
set -eu
LEAN_SYSROOT="$(lean --print-prefix)"
export LEAN_SYSROOT
export LD_LIBRARY_PATH="$LEAN_SYSROOT/lib/lean${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec /opt/dpc/analyzer/.lake/build/bin/dpc-analyze "$@"
