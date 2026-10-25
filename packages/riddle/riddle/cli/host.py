"""`riddle setup`, `riddle service`, `riddle demo`: making a machine the server.

The rest of the CLI assumes a server that already works. These are how one
comes to: the walk through everything it needs, the two halves as services
that outlive a reboot, and a server with no tablet behind it for showing the
app to somebody.
"""


def add(sub) -> None:
    setup = sub.add_parser("setup", help="set this machine up as a riddle server, step by step")
    setup.add_argument("--only", default=None, metavar="STEP",
                       help="one step, by a word of its title: tablet, agent, model, ...")
    setup.set_defaults(run=_setup)

    service = sub.add_parser("service", help="run the halves under systemd or launchd")
    verbs = service.add_subparsers(dest="verb", metavar="<verb>")

    install = verbs.add_parser("install", help="write the units or agents, enable and start them")
    install.add_argument("--voice-only", action="store_true",
                         help="only the page: for a demo server, or before there is a tablet")
    install.add_argument("--no-start", action="store_true", help="write and enable, do not start")
    install.set_defaults(run=_install)

    uninstall = verbs.add_parser("uninstall", help="stop them and remove the files")
    uninstall.set_defaults(run=_uninstall)

    show = verbs.add_parser("show", help="print what install would write")
    show.add_argument("half", choices=("voice", "diary"))
    show.set_defaults(run=_show)

    service.set_defaults(run=lambda a: service.print_help() or 1)

    demo = sub.add_parser("demo", help="a server with no tablet (RIDDLE_DEMO)")
    demo_verbs = demo.add_subparsers(dest="verb", metavar="<verb>")
    seed = demo_verbs.add_parser("seed", help="put a few invented pages on its timeline")
    seed.set_defaults(run=_seed)
    demo.set_defaults(run=lambda a: demo.print_help() or 1)


def _setup(args) -> int:
    from riddle import onboard

    return onboard.run(args)


def _install(args) -> int:
    from riddle import units

    names = ["voice"] if args.voice_only else ["voice", "diary"]
    return units.install(names, start=not args.no_start)


def _uninstall(args) -> int:
    from riddle import units

    return units.uninstall(["diary", "voice"])


def _show(args) -> int:
    from riddle import units

    print(units.show(args.half), end="")
    return 0


def _seed(args) -> int:
    from riddle import demo

    return demo.seed()
