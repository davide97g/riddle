"""`riddle diary` and `riddle voice`: the two long-lived halves.

Both get the same five verbs from the same builder, because they used to be
the same forty lines of bash twice and had already begun to drift.

`riddle start` is the pair of them: stop both, then bring both up. It is the
command for "make it work", and the only one that knows the order.

`riddle dev` is the same pair in this terminal, plus the client's dev server,
with both halves coming back when the python changes. The supervising is in
`riddle.dev`; this module only declares the flags.
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


def _start_both(args) -> int:
    """`riddle start`: the pair, from whatever state the machine is in.

    Both are stopped before either is started, because a half-running machine
    is exactly what fails confusingly. A second loop refuses to start while
    the first is still beating -- two ssh pipes into one digitizer interleave
    strokes -- and a voice server brought up beside a dying one joins the
    session it is about to lose.

    Then up in one order: the page first, the pen second. Either may create
    the session, but the loop is the half that will not start if the tablet
    is unreachable, and its failure is easier to read when the page is
    already there to show it.
    """
    from riddle import process

    code = 0
    for service in (process.DIARY, process.VOICE):
        print(f"-- {service.name}")
        process.stop(service, timeout=args.timeout)
    for service in (process.VOICE, process.DIARY):
        print(f"\n-- {service.name}")
        code |= process.start(service, append_log=args.append_log)
        if service is process.VOICE and not code:
            _say_where(service)
    if code:
        print("\nthat did not come up clean: riddle doctor, or riddle <half> log")
    return code


def _dev(args) -> int:
    from riddle import dev

    return dev.run(timeout=args.timeout, web=args.web, tailnet=args.tailnet)


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

    both = sub.add_parser("start", help="stop whatever is running, then bring both halves up")
    both.add_argument("--append-log", action="store_true",
                      help="keep the previous logs instead of rotating them")
    both.add_argument("--timeout", type=float, default=6.0, metavar="S",
                      help="how long each half gets to stop politely")
    both.set_defaults(run=_start_both)

    dev = sub.add_parser(
        "dev", help="like start, but in this terminal and reloaded when the code changes"
    )
    dev.add_argument("--no-web", dest="web", action="store_false",
                     help="leave the client out; the halves alone")
    dev.add_argument("--tailnet", action="store_true",
                     help="hot reload behind tailscale serve, for a phone")
    dev.add_argument("--timeout", type=float, default=6.0, metavar="S",
                     help="how long each half gets to stop politely")
    dev.set_defaults(run=_dev)

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
