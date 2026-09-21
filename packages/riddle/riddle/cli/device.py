"""`riddle device`, `riddle link`, `riddle snap`, `riddle taps`: the tablet."""

from pathlib import Path

from riddle.cli import CONSENT, HOST


def add(sub) -> None:
    device = sub.add_parser("device", help="the agent that runs on the tablet")
    verbs = device.add_subparsers(dest="verb", metavar="<verb>")

    build = verbs.add_parser(
        "build", parents=[HOST], help="cross-compile the agent and put it on the tablet"
    )
    build.add_argument("--no-deploy", action="store_true", help="build only")
    build.add_argument("-o", "--out", type=Path, default=None)
    build.set_defaults(run=_build)

    deploy = verbs.add_parser(
        "deploy", parents=[HOST], help="push the agent already built, without rebuilding"
    )
    deploy.add_argument("-o", "--out", type=Path, default=None)
    deploy.set_defaults(run=_deploy)

    link = sub.add_parser("link", help="probe the routes to the tablet and time the agent")
    link.add_argument("hosts", nargs="*", help="extra hosts to try")
    link.set_defaults(run=_link)

    snap = sub.add_parser(
        "snap", parents=[CONSENT, HOST], help="photograph the tablet's screen"
    )
    snap.add_argument("--scale", type=float, default=1.0)
    snap.add_argument("-o", "--out", type=Path, default=None)
    snap.set_defaults(run=_snap)

    taps = sub.add_parser("taps", help="the recorded toolbar presses used to pick a tool")
    tap_verbs = taps.add_subparsers(dest="verb", metavar="<verb>")

    learn = tap_verbs.add_parser(
        "learn", parents=[CONSENT, HOST], help="record the taps that select a tool"
    )
    learn.add_argument("name", help="what to call them, e.g. pen")
    learn.add_argument("--seconds", type=float, default=None, metavar="N")
    learn.set_defaults(run=_learn)

    listing = tap_verbs.add_parser("list", help="what has been recorded")
    listing.set_defaults(name=None, run=_show)

    show = tap_verbs.add_parser("show", help="the coordinates recorded for one tool")
    show.add_argument("name")
    show.set_defaults(run=_show)

    taps.set_defaults(name=None, run=_show)


def _build(args) -> int:
    from riddle.tools import build

    return build.run(args)


def _deploy(args) -> int:
    from riddle import config, paths
    from riddle.tools import build

    out = args.out or (paths.BUILD / "riddled")
    if not out.is_file():
        print(f"nothing built at {paths.relative(out)}: riddle device build")
        return 1
    host = args.host or config.get().ssh_host
    code = build.deploy(out, host)
    if not code:
        print(f"deployed to {host}")
    return code


def _link(args) -> int:
    from riddle import probe

    return probe.run(args)


def _snap(args) -> int:
    from riddle.tools import snap

    return snap.run(args)


def _learn(args) -> int:
    from riddle.tools import learn_taps

    return learn_taps.run(args)


def _show(args) -> int:
    from riddle.tools import learn_taps

    return learn_taps.show(args)
