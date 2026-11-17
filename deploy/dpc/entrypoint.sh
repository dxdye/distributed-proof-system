#!/bin/sh
# Entry point of the DPC web service image (deploy/dpc/Dockerfile).
#
# The state (audit log, vault, blobs) lives in $DPC_DATA, a Docker volume. On
# the first start it is seeded once from $DPC_SEED, a read-only copy of a data
# directory; later starts keep the volume's own state. Arguments are passed on
# to `dpc serve`.
set -eu
if [ -n "${DPC_SEED:-}" ] && [ -d "$DPC_SEED" ] && [ ! -e "$DPC_DATA/audit.sqlite" ]; then
  echo "dpc: seeding $DPC_DATA from $DPC_SEED"
  cp -a "$DPC_SEED"/. "$DPC_DATA"/
fi
exec pixi run --frozen python -m dpc serve --host 0.0.0.0 --port 8000 --data "$DPC_DATA" "$@"
