#!/usr/bin/env bash
# Check a backup against its own SHA256SUMS (bit-rot / bad-copy detection).
#   ./backup/verify.sh backup/rm2-<ts>
set -euo pipefail
SNAP="${1:?usage: verify.sh <backup/rm2-TIMESTAMP>}"
SNAP="$(cd "$SNAP" && pwd)"
[ -f "$SNAP/SHA256SUMS" ] || { echo "no SHA256SUMS in $SNAP" >&2; exit 1; }

echo "==> verifying $SNAP"
cd "$SNAP/tree"
if shasum -a 256 -c --quiet "$SNAP/SHA256SUMS"; then
  echo "==> OK: $(wc -l < "$SNAP/SHA256SUMS" | tr -d ' ') files match"
else
  echo "==> MISMATCH (see above)" >&2; exit 1
fi
