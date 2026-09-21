"""One command in front of everything: `riddle <group> <verb>`.

Every group is its own module and registers itself here. The rule that keeps
`riddle --help` instant, and keeps `riddle config` from opening an ssh pipe:
a cli module imports only argparse, pathlib and riddle.config at module
scope. Anything heavy -- numpy, PIL, the device -- is imported inside the
handler that needs it.
"""

import argparse
import sys

# Shared flags. Only parsers built with parents=[CONSENT] accept --yes, so the
# commands that can put ink on a page are one grep, and `riddle link --yes`
# is an error rather than a no-op.
CONSENT = argparse.ArgumentParser(add_help=False)
CONSENT.add_argument(
    "--yes", action="store_true", help="say out loud that this may touch the tablet"
)

HOST = argparse.ArgumentParser(add_help=False)
HOST.add_argument("--host", default=None, help="ssh host or alias (default: RM2_SSH_HOST)")


def build() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="riddle", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="store_true", help="print the version")
    sub = parser.add_subparsers(dest="group", metavar="<group>")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build()
    args = parser.parse_args(argv)
    if getattr(args, "version", False):
        from riddle import __version__

        print(__version__)
        return 0
    run = getattr(args, "run", None)
    if run is None:
        parser.print_help()
        return 1
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
