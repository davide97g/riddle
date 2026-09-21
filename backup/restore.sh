#!/usr/bin/env bash
# Push a backup back onto the reMarkable.
#
# DRY RUN BY DEFAULT. It prints what would change and writes nothing.
# To actually write:  RESTORE_APPLY=1 ./backup/restore.sh <snapshot> [subpath]
#
#   ./backup/restore.sh backup/rm2-<ts>                      # dry run, everything
#   ./backup/restore.sh backup/rm2-<ts> home/root/.local     # dry run, one subtree
#   RESTORE_APPLY=1 ./backup/restore.sh backup/rm2-<ts> home/root/.local
#
# This only ADDS and OVERWRITES. It never deletes files that exist on the
# tablet but not in the backup (no --delete). Restoring the document store
# therefore merges; see README.md "Restoring" for the full-replace procedure.
set -euo pipefail

HOST="${RM2_SSH_HOST:-rm2}"
SNAP="${1:?usage: restore.sh <backup/rm2-TIMESTAMP> [subpath under tree/]}"
SUB="${2:-}"
SNAP="$(cd "$SNAP" && pwd)"
SRC="$SNAP/tree"
[ -d "$SRC" ] || { echo "no tree/ in $SNAP" >&2; exit 1; }

if [ -n "$SUB" ]; then
  SRC="$SRC/${SUB%/}"
  [ -e "$SRC" ] || { echo "no such subpath: $SUB" >&2; exit 1; }
  REMOTE="/$(dirname "${SUB%/}")"
else
  REMOTE="/"
fi

APPLY="${RESTORE_APPLY:-0}"
echo "==> snapshot: $SNAP"
echo "==> source:   $SRC"
echo "==> target:   $HOST:$REMOTE"
[ "$APPLY" = 1 ] && echo "==> MODE: APPLY (writing to device)" || echo "==> MODE: dry run"

# xochitl caches the document store in memory and rewrites it on exit, so it
# must be stopped before the store is touched, and started after.
TOUCHES_STORE=0
case "${SUB:-home/root}" in home/root*|"") TOUCHES_STORE=1 ;; esac

if [ "$APPLY" = 1 ]; then
  read -r -p "Write to $HOST:$REMOTE ? type yes: " a
  [ "$a" = yes ] || { echo "aborted"; exit 1; }
  if [ "$TOUCHES_STORE" = 1 ]; then
    echo "==> stopping xochitl"
    ssh "$HOST" 'systemctl stop xochitl'
  fi
fi

# --no-o --no-g is deliberate. The backup was extracted on macOS, so the local
# copies are owned by the desktop user, not root. Letting rsync push that
# ownership would chown the tablet's files to uid 501 and break it. Without
# those flags rsync leaves existing owners alone, and files it creates are
# owned by the remote ssh user (root). Original ownership is recorded in
# OWNERSHIP.txt if you ever need to check it.
RSYNC_OPTS=(-a --no-o --no-g)
[ "$APPLY" = 1 ] || RSYNC_OPTS+=(--dry-run --itemize-changes)

rsync "${RSYNC_OPTS[@]}" "$SRC" "$HOST:$REMOTE/" || true

if [ "$APPLY" = 1 ]; then
  ssh "$HOST" 'sync'
  if [ "$TOUCHES_STORE" = 1 ]; then
    echo "==> starting xochitl"
    ssh "$HOST" 'systemctl start xochitl'
  fi
  echo "==> restored"
else
  echo "==> dry run only. Re-run with RESTORE_APPLY=1 to write."
fi
