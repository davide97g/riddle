"""`riddle backup`: snapshots of the tablet, which stay on this machine.

The scripts underneath stay shell -- tar over ssh and `shasum -c` are things
shell does better -- but they are run from here so they see the configured
ssh host. backup.sh and inventory.sh sourced no .env, so with RM2_SSH_HOST
pointing at wifi they quietly went looking down the usb cable.

A snapshot holds the tablet's private ssh keys, its shell history and every
notebook on it. It is written under var/, which is gitignored, and it is
never committed.
"""

from pathlib import Path


def add(sub) -> None:
    backup = sub.add_parser("backup", help="snapshots of the tablet")
    verbs = backup.add_subparsers(dest="verb", metavar="<verb>")

    create = verbs.add_parser("create", help="copy the tablet into var/backups")
    create.add_argument("--mode", choices=("tar", "rsync"), default="tar")
    create.add_argument("--host", default=None)
    create.set_defaults(run=_create)

    inventory = verbs.add_parser("inventory", help="a read-only survey of what is on it")
    inventory.add_argument("--host", default=None)
    inventory.set_defaults(run=_inventory)

    listing = verbs.add_parser("list", help="snapshots on disk")
    listing.set_defaults(run=_list)

    verify = verbs.add_parser("verify", help="check a snapshot against its checksums")
    verify.add_argument("snapshot", type=Path)
    verify.set_defaults(run=_verify)

    restore = verbs.add_parser("restore", help="put a snapshot back (dry run unless --apply)")
    restore.add_argument("snapshot", type=Path)
    restore.add_argument("subpath", nargs="?", default=None)
    restore.add_argument("--apply", action="store_true", help="actually write to the tablet")
    restore.set_defaults(run=_restore)

    backup.set_defaults(run=_list)


def _script(name: str, argv: list[str], extra: dict | None = None) -> int:
    import os
    import subprocess
    import sys

    from riddle import config, paths

    cfg = config.get()
    env = {
        **os.environ,
        "RM2_SSH_HOST": cfg.ssh_host,
        "BACKUP_DIR": str(paths.BACKUPS),
        "RIDDLE_PYTHON": sys.executable,
        **(extra or {}),
    }
    script = paths.ROOT / "scripts" / "backup" / name
    return subprocess.run([str(script), *argv], env=env, cwd=paths.ROOT).returncode


def _create(args) -> int:
    extra = {"BACKUP_MODE": args.mode}
    if args.host:
        extra["RM2_SSH_HOST"] = args.host
    return _script("backup.sh", [], extra)


def _inventory(args) -> int:
    extra = {"RM2_SSH_HOST": args.host} if args.host else {}
    return _script("inventory.sh", [], extra)


def _list(args) -> int:
    from riddle import paths

    found = sorted(p for p in paths.BACKUPS.glob("*") if p.is_dir())
    if not found:
        print(f"no snapshots in {paths.relative(paths.BACKUPS)}")
        return 1
    for path in found:
        size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        print(f"{paths.relative(path)}  {size // (1024 * 1024)}M")
    return 0


def _verify(args) -> int:
    return _script("verify.sh", [str(args.snapshot)])


def _restore(args) -> int:
    argv = [str(args.snapshot)] + ([args.subpath] if args.subpath else [])
    return _script("restore.sh", argv, {"RESTORE_APPLY": "1" if args.apply else "0"})
