#!/usr/bin/env bash
# Read-only survey of the reMarkable. Writes a manifest of what is on the device
# to backup/inventory-<ts>/ on the host. Touches nothing on the tablet.
set -euo pipefail

HOST="${RM2_SSH_HOST:-rm2}"
HERE="$(cd "$(dirname "$0")" && pwd)"
TS="$(date +%Y%m%d-%H%M%S)"
OUT="$HERE/inventory-$TS"
mkdir -p "$OUT"

echo "==> host: $HOST"
echo "==> out:  $OUT"

run() { ssh "$HOST" "$1" 2>&1 || true; }

run 'cat /etc/version; echo; cat /usr/share/remarkable/update.conf 2>/dev/null; echo; uname -a' > "$OUT/version.txt"
run 'df -h' > "$OUT/df.txt"
run 'du -sh /home/root /home/root/.local/share/remarkable/xochitl /usr/share/remarkable /etc 2>/dev/null' > "$OUT/sizes.txt"

# Per-path file list. busybox find has no -printf, so: find for names, du -ak for sizes.
for p in /home/root /usr/share/remarkable /etc /opt; do
  name="$(echo "${p#/}" | tr / _)"
  run "find '$p' -xdev \\( -type f -o -type l \\) -print 2>/dev/null | LC_ALL=C sort" > "$OUT/files-$name.txt"
  run "du -ak '$p' 2>/dev/null | LC_ALL=C sort -k2" > "$OUT/du-$name.txt"
done

# Dump every document .metadata verbatim; parse on the host so names with
# spaces/unicode survive.
run 'cd /home/root/.local/share/remarkable/xochitl 2>/dev/null && \
     for f in *.metadata; do [ -e "$f" ] || continue; echo "===FILE=== $f"; cat "$f"; echo; done' \
  > "$OUT/metadata.raw"

python3 - "$OUT" <<'PY'
import json, os, sys
out = sys.argv[1]
raw = open(os.path.join(out, "metadata.raw"), encoding="utf-8", errors="replace").read()
docs, cur, buf = [], None, []

def flush():
    if cur is None:
        return
    try:
        m = json.loads("".join(buf))
    except Exception:
        m = {}
    docs.append({"uuid": cur[: -len(".metadata")], **m})

for line in raw.splitlines():
    if line.startswith("===FILE==="):
        flush()
        cur, buf = line.split(" ", 1)[1].strip(), []
    elif cur is not None:
        buf.append(line)
flush()

by_id = {d["uuid"]: d for d in docs}

def path_of(d):
    parts, seen = [], set()
    while d and d["uuid"] not in seen:
        seen.add(d["uuid"])
        parts.append(d.get("visibleName", "?"))
        d = by_id.get(d.get("parent") or "")
    return "/".join(reversed(parts))

rows = sorted(
    (path_of(d), d.get("type", "?"), d["uuid"], d.get("deleted", False))
    for d in docs
)
with open(os.path.join(out, "documents.tsv"), "w", encoding="utf-8") as f:
    f.write("path\ttype\tuuid\tdeleted\n")
    for p, t, u, dl in rows:
        f.write(f"{p}\t{t}\t{u}\t{dl}\n")
print(f"    {len(rows)} documents")
PY

{
  echo "# reMarkable inventory $TS"
  echo
  echo '## Version'; echo; sed 's/^/    /' "$OUT/version.txt"
  echo; echo '## Disk'; echo; sed 's/^/    /' "$OUT/df.txt"
  echo; echo '## Sizes'; echo; sed 's/^/    /' "$OUT/sizes.txt"
  echo; echo '## File counts'; echo
  for f in "$OUT"/files-*.txt; do
    printf '    %-28s %s\n' "$(basename "$f")" "$(wc -l < "$f" | tr -d ' ') files"
  done
  echo; echo '## Documents'; echo; sed 's/^/    /' "$OUT/documents.tsv"
} > "$OUT/SUMMARY.md"

echo "==> wrote $OUT/SUMMARY.md"
