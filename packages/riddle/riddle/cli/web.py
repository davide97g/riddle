"""`riddle web`: the client's own toolchain, with the server's config handed in.

vite.config.ts reads RIDDLE_SERVER and RIDDLE_TAILNET from its environment.
Rather than teach it where those come from, they are injected here -- which
is also why RIDDLE_SERVER is derived from the host and port by default, so
moving the port cannot silently break the dev proxy.
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
    import os
    import shutil
    import subprocess

    from riddle import config, paths

    if not shutil.which("bun"):
        print("bun is not installed: brew install oven-sh/bun/bun")
        return 1
    cfg = config.get()
    where = paths.ROOT / "apps" / "web"
    env = {
        **os.environ,
        "RIDDLE_SERVER": cfg.server,
        "RIDDLE_TAILNET": "1" if (cfg.tailnet or getattr(args, "tailnet", False)) else "0",
    }
    return subprocess.run(["bun", *argv], cwd=where, env=env).returncode
