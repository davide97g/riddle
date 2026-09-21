# reMarkable backup

A full, read-only copy of the tablet, taken over the existing `rm2` ssh alias.
Nothing on the device was written, moved, renamed or deleted — every operation
here is `find`, `cat`, `du` or `tar -c`.

## What is here

```
scripts/backup/
  inventory.sh          survey the device, write a manifest (read-only, no copy)
  backup.sh             copy the device into var/backups/rm2-<ts>/
  verify.sh             re-check a snapshot against its own SHA256SUMS
  restore.sh            push a snapshot back to the device (dry run by default)

var/backups/            where snapshots land; gitignored, never committed
  inventory-<ts>/       output of inventory.sh
  rm2-<ts>/             a snapshot
```

A snapshot looks like:

```
rm2-<ts>/
  tree/                 the copied filesystem, rooted at /
    home/root/...
    usr/share/remarkable/...
    etc/...
  MANIFEST.txt          host, timestamp, paths, file count, size
  SHA256SUMS            sha256 of every regular file under tree/
  OWNERSHIP.txt         ls -ldn of every path AS IT IS ON THE DEVICE
  version.txt           /etc/version, uname, update.conf
  partitions.txt        /proc/mounts and /proc/partitions (reference only)
  enabled-units.txt     enabled systemd units
```

## What a snapshot contains

Paths copied, and why:

| Path | Why |
|---|---|
| `/home/root` | the document store, plus templates, ssh keys and the `riddle` agent |
| `/usr/share/remarkable` | stock templates, splash screens, `update.conf`, the USB web UI |
| `/opt` | third-party installs (toltec), if present |
| `/etc` | system config, network, systemd units, dropbear |

The bulk of it is `tree/home/root/.local/share/remarkable/xochitl`: xochitl's
flat document store, where each document is a uuid with sidecar files
(`.metadata`, `.content`, `.pagedata`, `.pdf`, and a directory of per-page
`.rm` stroke data). `inventory-<ts>/documents.tsv` maps those uuids back to
readable paths by walking each `.metadata`'s `parent` chain.

Each snapshot records its own numbers in `MANIFEST.txt`, and a `SNAPSHOT.md`
alongside it if you want to keep notes.

## How it was done

1. **Reachability.** The tablet is only up when it is plugged in over USB *and*
   *Settings → Storage → USB web interface* is on; that is what brings up
   `10.11.99.1`. With it off there is no network interface at all and ssh just
   times out.

2. **Inventory first** (`inventory.sh`) — version, `df`, `du`, a full file list
   per path, and every `.metadata` dumped verbatim. Two portability notes that
   cost a rewrite: the tablet's `find` is busybox and has no `-printf`, so sizes
   come from `du -ak` instead; and document names contain spaces and non-ASCII,
   so the JSON is parsed on the host in Python rather than with `sed` on the
   device.

3. **`sync` on the device**, to flush recent writes to disk. xochitl was
   deliberately **left running** — a live copy of the store is fine for a
   backup, and stopping it would discard whatever page is open in memory.

4. **`tar -c` over ssh**, streamed straight into `tar -x` on the Mac. `rsync` is
   supported via `BACKUP_MODE=rsync`, but tar is the default: this Mac ships
   openrsync, which lacks `-HAX` and `--info=progress2`.

5. **Ownership recorded separately** (`OWNERSHIP.txt`). Extracting as a normal
   macOS user cannot preserve root ownership, so the local copies are owned by
   the desktop user. On a stock device every path is owned by `0:0`, which is
   why restore never pushes ownership (see below).

6. **Checksums** (`SHA256SUMS`), then verified with `verify.sh`. Worth also
   comparing file counts against the device path by path, counting regular
   files and symlinks separately, before trusting a snapshot.

### Re-running

```bash
riddle backup inventory                     # survey only, copies nothing
riddle backup create                        # new snapshot
riddle backup verify var/backups/rm2-<ts>   # re-check checksums
```

`RM2_SSH_HOST` overrides the ssh alias. `BACKUP_MODE=rsync` switches transfer.
Snapshots are timestamped, so a new run never touches an old one.

## What is NOT covered

This is a **file-level** backup, not a disk image. It will not recover a device
that will not boot.

- No raw partition image. `/dev/mmcblk2p4` (`/home`) and the rootfs are not
  imaged; `partitions.txt` only records the layout for reference.
- No bootloader / U-Boot (`/var/lib/uboot`), no kernel, no recovery partition.
- Nothing outside the four paths above — `/var`, `/usr` (beyond
  `usr/share/remarkable`), and `/lib` are stock and come back with a reflash.

For a bootable-device disaster, reflash the stock image and then restore
`/home/root` from here.

## Restoring

`restore.sh` is **dry run by default** and prints what it would change:

```bash
riddle backup restore var/backups/rm2-<ts>                   # everything
riddle backup restore var/backups/rm2-<ts> home/root/.local  # one subtree
```

To actually write, set `RESTORE_APPLY=1`; it then asks for a typed `yes`:

```bash
riddle backup restore var/backups/rm2-<ts> home/root/.local --apply
```

What it does, and the reasoning:

- **Stops `xochitl` before touching `/home/root`, starts it after.** xochitl
  holds the document store in memory and rewrites it on exit; writing under it
  while it runs means your restored files get overwritten by its stale copy.
- **Never pushes ownership** (`--no-o --no-g`). The local copies are owned by
  the desktop user; pushing that would chown the tablet's files to uid 501 and
  break it. Existing owners are left alone, and files rsync creates are owned by
  the remote ssh user, which is root — matching `OWNERSHIP.txt`.
- **Never deletes.** There is no `--delete`, on purpose. It only adds and
  overwrites.

### Reverting a single document

Cleanest path, because the store is flat and uuid-keyed. Find the uuid in
`inventory-<ts>/documents.tsv`, then:

```bash
ssh rm2 'systemctl stop xochitl'
UUID=<uuid>; SNAP=var/backups/rm2-<ts>
rsync -a --no-o --no-g \
  "$SNAP"/tree/home/root/.local/share/remarkable/xochitl/$UUID* \
  rm2:/home/root/.local/share/remarkable/xochitl/
ssh rm2 'sync && systemctl start xochitl'
```

### Full-replace of the document store

`restore.sh` merges rather than replaces, so a document created *after* the
snapshot survives a restore. If you genuinely want the store to be exactly as
it was, move the live one aside first — move, not delete, so it is recoverable:

```bash
ssh rm2 'systemctl stop xochitl && cd /home/root/.local/share/remarkable && \
         mv xochitl xochitl.old.$(date +%s) && mkdir xochitl'
riddle backup restore --apply var/backups/rm2-<ts> \
  home/root/.local/share/remarkable/xochitl
```

Check the tablet looks right, *then* remove the `xochitl.old.*` directory. The
rootfs is small and typically near full, but the store lives on the roomy
`/home` partition, so the spare copy fits there. Check `df.txt` first.

### After any restore

The tablet syncs to reMarkable's cloud if that is enabled. Restoring an older
version of a document can propagate — turn sync off before a large restore if
you do not want that, and watch what the cloud does before re-enabling.

## Caveats

- **Live copy.** The store was read with xochitl running. If a page had been
  written seconds earlier it could in principle be caught mid-write; the `sync`
  makes this unlikely, not impossible.
- **`tree/home/root/.ssh` and `tree/etc/dropbear` contain private keys**, and
  `.bash_history` is in there too. This snapshot is secrets-bearing — keep it
  off any shared drive and out of version control (`.gitignore` covers it).
- **`.cache` is included** for completeness even though xochitl regenerates it. Add `'./root/.cache'` to `EXCLUDES` in `scripts/backup/backup.sh` to skip it.
- **Firmware-version coupling.** A snapshot's `/etc` matches the firmware it
  came from (recorded in `version.txt`). Pushing it onto a different firmware is
  asking for trouble; restore `/home/root` freely, restore `/etc` only onto the
  same version.
