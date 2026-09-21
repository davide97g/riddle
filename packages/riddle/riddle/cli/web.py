"""`riddle web`: the client's own toolchain, with the server's config handed in.

vite.config.ts reads RIDDLE_SERVER and RIDDLE_TAILNET from its environment;
`riddle.toolchain` is the one place that spells them, so moving the port
cannot silently break the dev proxy.
"""


def add(sub) -> None:
    web = sub.add_parser("web", help="the page you speak into, as a front end")
    verbs = web.add_subparsers(dest="verb", metavar="<verb>")

    install = verbs.add_parser("install", help="bun install")
    install.set_defaults(run=lambda a: _bun(["install"], a))

    dev = verbs.add_parser("dev", help="vite dev server, proxying to the python server")
    dev.add_argument("--tailnet", action="store_true", help="hot reload behind tailscale serve")
    dev.set_defaults(run=lambda a: _bun(["run", "dev"], a))

    build = verbs.add_parser("build", help="type-check and build apps/web/dist")
    build.set_defaults(run=lambda a: _bun(["run", "build"], a))

    lint = verbs.add_parser("lint", help="oxlint")
    lint.set_defaults(run=lambda a: _bun(["run", "lint"], a))

    web.set_defaults(run=lambda a: _bun(["run", "build"], a))


def _bun(argv: list[str], args) -> int:
    import subprocess

    from riddle import toolchain

    if not toolchain.have_bun():
        print(toolchain.MISSING)
        return 1
    env = toolchain.env(tailnet=getattr(args, "tailnet", False))
    return subprocess.run(["bun", *argv], cwd=toolchain.WHERE, env=env).returncode
