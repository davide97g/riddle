"""One command in front of everything: `riddle <group> <verb>`.

There were three shell launchers, twelve scripts you had to invoke by path
with the right interpreter, and a `--yes` flag that worked by looking at the
raw argument list. Now there is one entry point, and the flag is declared in
exactly one place.

Two rules keep it honest. A `cli` module imports only argparse, pathlib and
`riddle.config` at module scope -- anything heavy (numpy, PIL, the device)
is imported inside the handler that needs it, so `riddle --help` is instant
and `riddle config` never opens an ssh pipe. And only parsers built with
`parents=[CONSENT]` accept `--yes`, which makes the commands that can put
ink on a page a single grep, and makes `riddle link --yes` an error rather
than a no-op.
"""

import argparse
import sys

CONSENT = argparse.ArgumentParser(add_help=False)
CONSENT.add_argument(
    "--yes",
    action="store_true",
    help="say out loud that this may touch the tablet",
)

HOST = argparse.ArgumentParser(add_help=False)
HOST.add_argument(
    "--host",
    default=None,
    metavar="SSH",
    help="ssh host or alias to use instead of RM2_SSH_HOST",
)

GROUPS = (
    "services",
    "device",
    "ink",
    "voice_tools",
    "web",
    "backup",
    "introspect",
)


def build() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="riddle",
        description="A Tom Riddle diary for the reMarkable 2.",
    )
    parser.add_argument("-V", "--version", action="store_true", help="print the version")
    parser.add_argument(
        "--env",
        metavar="PATH",
        default=None,
        help="read this dotenv file instead of ./.env",
    )
    parser.add_argument(
        "--no-env", action="store_true", help="ignore .env; use the environment only"
    )
    sub = parser.add_subparsers(dest="group", metavar="<command>")

    from importlib import import_module

    for name in GROUPS:
        import_module(f"riddle.cli.{name}").add(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build()
    args = parser.parse_args(argv)

    if args.version:
        from riddle import __version__

        print(__version__)
        return 0

    from pathlib import Path

    from riddle import config

    config.load(Path(args.env) if args.env else None, use_dotenv=not args.no_env)

    run = getattr(args, "run", None)
    if run is None:
        parser.print_help()
        return 1
    try:
        return int(run(args) or 0)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
