#!/bin/sh
# Restart the read-only monitor if it exits. This script does not sign or send transactions.
set -u
cd "$(dirname "$0")"
OUT="${CABAL_WATCH_OUT:-/workspace/cabal-watch/out}"
while true; do
  python3 -m monitor --out "$OUT" || echo "cabal-watch monitor exited ($?), restarting in 10s" >&2
  sleep 10
done
