#!/usr/bin/env bash
# Copy the reMarkable's user data and system config to backup/rm2-<ts>/.
# Copy only: nothing on the tablet is written, moved or deleted.
#
#   ./backup/backup.sh                 # tar over ssh (default, most portable)
#   BACKUP_MODE=rsync ./backup/backup.sh
set -euo pipefail

HOST="${RM2_SSH_HOST:-rm2}"
# Snapshots hold the tablet's private keys and every notebook on it, so
# they are written under var/, which is gitignored whole and never
# committed. riddle backup passes BACKUP_DIR; the default is for running
# this script by hand.
HERE="$(cd "$(dirname "$0")/../.." && pwd)"
OUTDIR="${BACKUP_DIR:-$HERE/var/backups}"
mkdir -p "$OUTDIR"
TS="${BACKUP_TS:-$(date +%Y%m%d-%H%M%S)}"
OUT="$OUTDIR/rm2-$TS"
MODE="${BACKUP_MODE:-tar}"

# Paths pulled from the device.
PATHS=(
  /home/root             # notebooks, templates, user files, the riddle agent
  /usr/share/remarkable  # stock templates, splash screens, update.conf
  /etc                   # system config, network, systemd units
  /opt                   # third-party installs (toltec etc.), if present
)

# Paths skipped inside the above. Empty by default: a complete copy is the point.
# Add e.g. './root/.cache' (xochitl's regenerable page/thumbnail cache) to trim.
EXCLUDES=( )

mkdir -p "$OUT/tree"
echo "==> host:     $HOST"
echo "==> out:      $OUT"
echo "==> transfer: $MODE"

# Flush recent writes to disk. xochitl is deliberately left running: a live copy
# of the document store is fine, and stopping it would drop the open page.
ssh "$HOST" 'sync' || true

for p in "${PATHS[@]}"; do
  if ! ssh "$HOST" "[ -e '$p' ]"; then echo "    skip $p (absent)"; continue; fi
  echo "    pull $p"
  parent="$(dirname "$p")"
  base="$(basename "$p")"
  dest="$OUT/tree$parent"
  mkdir -p "$dest"
  if [ "$MODE" = rsync ]; then
    rsync -a --numeric-ids "$HOST:$p" "$dest/"
  else
    ex=""
    for e in ${EXCLUDES[@]+"${EXCLUDES[@]}"}; do ex="$ex --exclude=${e}"; done
    # shellcheck disable=SC2029
    ssh "$HOST" "cd '$parent' && tar $ex -cf - './$base'" | tar -C "$dest" -xf -
  fi
done

# Reference-only system state. We do NOT image raw partitions.
ssh "$HOST" 'cat /proc/mounts; echo; cat /proc/partitions' > "$OUT/partitions.txt" 2>&1 || true
ssh "$HOST" 'cat /etc/version; echo; uname -a; echo; cat /usr/share/remarkable/update.conf 2>/dev/null' \
  > "$OUT/version.txt" 2>&1 || true
ssh "$HOST" 'systemctl list-unit-files --state=enabled --no-pager' > "$OUT/enabled-units.txt" 2>&1 || true

# Ownership and mode of every path, as it is ON THE DEVICE. tar-over-ssh
# extraction on macOS cannot preserve root ownership, so record it separately.
echo "==> recording ownership"
: > "$OUT/OWNERSHIP.txt"
for p in "${PATHS[@]}"; do
  ssh "$HOST" "[ -e '$p' ] && find '$p' -xdev -exec ls -ldn {} + 2>/dev/null" \
    >> "$OUT/OWNERSHIP.txt" 2>/dev/null || true
done

# Checksums, so a restore can be verified against what was taken.
echo "==> hashing"
( cd "$OUT/tree" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum -a 256 ) \
  > "$OUT/SHA256SUMS" 2>/dev/null || true

{
  echo "source_host: $HOST"
  echo "taken_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "transfer: $MODE"
  echo "paths:"
  printf '  - %s\n' "${PATHS[@]}"
  if [ ${#EXCLUDES[@]} -gt 0 ]; then
    echo "excluded:"; printf '  - %s\n' "${EXCLUDES[@]}"
  else
    echo "excluded: (none)"
  fi
  echo "files: $(wc -l < "$OUT/SHA256SUMS" | tr -d ' ')"
  echo "size: $(du -sh "$OUT/tree" | cut -f1)"
} > "$OUT/MANIFEST.txt"

cat "$OUT/MANIFEST.txt"
echo "==> done: $OUT"
