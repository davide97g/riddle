"""`riddle diary` and `riddle voice`: the two long-lived halves.

Both get the same five verbs from the same builder, because they used to be
the same forty lines of bash twice and had already begun to drift.
"""

def _verbs(sub, service, extra_help: str = "") -> None:
    group = sub.add_parser(service.name, help=extra_help)
    verbs = group.add_subparsers(dest="verb", metavar="<verb>")

    start = verbs.add_parser("start", help="bring it up in the background")
    start.add_argument(
        "--foreground",
        action="store_true",
        help="run it in this terminal instead, with no pidfile",
    )
    start.add_argument(
        "--append-log", action="store_true", help="keep the previous log instead of rotating it"
    )
    start.set_defaults(run=lambda a, s=service: _start(a, s))

    stop = verbs.add_parser("stop", help="ask it to stop, then insist")
    stop.add_argument("--timeout", type=float, default=6.0, metavar="S")
    stop.set_defaults(run=lambda a, s=service: _stop(a, s))

    status = verbs.add_parser("status", help="is it running, and what did it last say")
    status.set_defaults(run=lambda a, s=service: _status(a, s))

    log = verbs.add_parser("log", help="show or follow the log")
    log.add_argument("-n", "--lines", type=int, default=40)
    log.add_argument("-f", "--follow", action="store_true")
    log.set_defaults(run=lambda a, s=service: _log(a, s))

    restart = verbs.add_parser("restart", help="stop, then start")
    restart.add_argument("--append-log", action="store_true")
    restart.set_defaults(foreground=False, timeout=6.0)
    restart.set_defaults(run=lambda a, s=service: _restart(a, s))

    group.set_defaults(run=lambda a, s=service: _status(a, s), verb="status")
    return verbs


def _start(args, service) -> int:
    from riddle import process

    if getattr(args, "foreground", False):
        return process.run_foreground(service)
    return process.start(service, append_log=getattr(args, "append_log", False))


def _stop(args, service) -> int:
    from riddle import process

    return process.stop(service, timeout=getattr(args, "timeout", 6.0))


def _status(args, service) -> int:
    from riddle import process

    code = process.status(service)
    if service.name == "voice":
        _say_where(service)
    return code


def _log(args, service) -> int:
    from riddle import process

    return process.log(service, lines=args.lines, follow=args.follow)


def _restart(args, service) -> int:
    _stop(args, service)
    return _start(args, service)


def _say_where(service) -> None:
    """The voice server is only useful if you know how to reach it."""
    from riddle import config, tailnet

    cfg = config.get()
    if not tailnet.port_open(cfg.web_host, cfg.web_port):
        return
    try:
        served = tailnet.served_ports()
    except tailnet.TailscaleError:
        return
    if cfg.web_port in served:
        try:
            print(f"shared at https://{tailnet.self_dns_name()}/")
        except tailnet.TailscaleError:
            pass
    else:
        print(f"on http://{cfg.web_host}:{cfg.web_port} -- `riddle voice share` for a phone")


def add(sub) -> None:
    from riddle.process import DIARY, VOICE

    _verbs(sub, DIARY, "the loop that watches the page and answers on it")
    verbs = _verbs(sub, VOICE, "the page you speak into")

    share = verbs.add_parser("share", help="put a real certificate in front of it, for a phone")
    share.add_argument(
        "--force",
        action="store_true",
        help="share even though nothing is listening on the port",
    )
    share.set_defaults(run=_share)

    unshare = verbs.add_parser("unshare", help="take the certificate down again")
    unshare.set_defaults(run=_unshare)


def _share(args) -> int:
    """A browser will not hand a page the microphone over plain http.

    Tailscale holds a real certificate for this machine's tailnet name and
    proxies it to loopback, so nothing here has to grow an ssl import.
    """
    from riddle import config, process, tailnet

    cfg = config.get()
    if not args.force:
        listening = process.alive(process.VOICE) and tailnet.port_open(
            cfg.web_host, cfg.web_port
        )
        if not listening:
            print(
                "voice is not running, so a certificate would front a dead port "
                "and the phone would show a 502.\n"
                "start it first: riddle voice start   (or pass --force)",
            )
            return 1
    try:
        url = tailnet.serve(cfg.web_port)
    except tailnet.TailscaleError as exc:
        print(f"tailscale: {exc}")
        return 1
    print(f"open {url} on your phone")
    print("take it down again with: riddle voice unshare")
    return 0


def _unshare(args) -> int:
    from riddle import tailnet

    try:
        ports = tailnet.served_ports()
        if ports:
            print(f"serving {', '.join(str(p) for p in ports)}; taking all of it down")
        tailnet.reset()
    except tailnet.TailscaleError as exc:
        print(f"tailscale: {exc}")
        return 1
    print("not shared any more")
    return 0
