"""Check everything that can be wrong without saying so.

Most of what breaks in this project produces no error message. A missing
`taps.json` makes the pen-selection tap a silent no-op, and with the lasso
active a page of handwriting becomes a page of selections. A database path
that resolves differently in the two halves makes sqlite create a second
empty file, and the page simply stays empty. A font that does not resolve
falls back to a different hand. A stale editable install means your edits
appear to do nothing at all.

Every one of those is one assertion here, which is the point of the command.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from riddle import config, paths

OK, WARN, FAIL = "ok", "warn", "fail"


@dataclass
class Result:
    status: str
    group: str
    name: str
    detail: str = ""
    fix: str = ""


def _version(binary: str, *args: str) -> str:
    try:
        done = subprocess.run(
            [binary, *args], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (done.stdout or done.stderr).strip().splitlines()[0] if (done.stdout or done.stderr) else ""


def check_tools() -> list[Result]:
    wanted = [
        ("zig", ["version"], "brew install zig", True),
        ("bun", ["--version"], "brew install oven-sh/bun/bun", True),
        ("claude", ["--version"], "install the claude CLI", True),
        ("parakeet-cli", ["--help"], "install parakeet-cli for the microphone", False),
        ("tailscale", ["version"], "install tailscale to reach the page from a phone", False),
        ("ssh", ["-V"], "install openssh", True),
    ]
    out = []
    for binary, args, fix, required in wanted:
        where = shutil.which(binary)
        if where:
            out.append(Result(OK, "tools", binary, _version(binary, *args)[:60]))
        else:
            out.append(
                Result(FAIL if required else WARN, "tools", binary, "not on PATH", fix)
            )
    return out


def check_python() -> list[Result]:
    import sys

    import riddle

    out = [Result(OK, "python", "interpreter", sys.version.split()[0])]
    where = Path(riddle.__file__).resolve()
    if paths.ROOT in where.parents:
        out.append(Result(OK, "python", "install", f"editable, {paths.relative(where.parent)}"))
    else:
        out.append(
            Result(
                FAIL, "python", "install",
                f"riddle imports from {where}, not this checkout -- your edits do nothing",
                "pip install -e packages/riddle",
            )
        )
    for name in ("numpy", "PIL"):
        try:
            __import__(name)
            out.append(Result(OK, "python", name))
        except ImportError:
            out.append(Result(FAIL, "python", name, "not importable",
                              "pip install -e packages/riddle"))
    return out


def check_config() -> list[Result]:
    out = []
    env_file = paths.ROOT / ".env"
    if env_file.is_file():
        out.append(Result(OK, "config", ".env", f"{len(config.read_dotenv(env_file))} keys"))
    else:
        out.append(Result(WARN, "config", ".env", "missing",
                          "cp .env.example .env"))
    for problem in config.check():
        out.append(Result(WARN, "config", "contents", problem))
    cfg = config.get()
    out.append(Result(OK, "config", "root", str(paths.ROOT)))
    out.append(Result(OK, "config", "db", str(cfg.db)))
    out.extend(_mind(cfg))
    return out


def _mind(cfg) -> list[Result]:
    """Who answers, and whether it can.

    A missing key is the failure that looks like nothing: the loop starts,
    the pen works, and every turn ends with an error event nobody is watching
    for. So it is said here, before a page is written on.
    """
    if cfg.mind == "claude":
        return [Result(OK, "config", "mind", f"claude, {cfg.model}")]
    if cfg.mind != "deepseek":
        return [Result(FAIL, "config", "mind", f"{cfg.mind!r} is not a mind",
                       "RIDDLE_MIND is 'deepseek' or 'claude'")]
    out = [Result(OK, "config", "mind", f"deepseek, {cfg.deepseek_model}")]
    if cfg.deepseek_key:
        out.append(Result(OK, "config", "deepseek key", f"set, {len(cfg.deepseek_key)} chars"))
    else:
        out.append(Result(FAIL, "config", "deepseek key", "not set",
                          "put RIDDLE_DEEPSEEK_KEY in .env"))
    # The page is read by a model that can see, whichever mind answers.
    out.append(Result(OK, "config", "eyes", cfg.eyes_model))
    return out


def check_assets() -> list[Result]:
    cfg = config.get()
    out = []
    for label, name in (("body", cfg.font_body), ("accent", cfg.font_accent)):
        jhf = paths.FONT_DIR / f"{name}.jhf"
        ttf = paths.FONT_DIR / f"{name}.ttf"
        if ttf.is_file():
            out.append(Result(OK, "assets", f"font {label}", f"{name} (skeletonised ttf)"))
        elif jhf.is_file():
            out.append(Result(OK, "assets", f"font {label}", f"{name} (hershey)"))
        else:
            out.append(Result(FAIL, "assets", f"font {label}",
                              f"no {name}.ttf or {name}.jhf in {paths.relative(paths.FONT_DIR)}"))

    # The one whose failure looks like a rendering bug: with no pen tap
    # recorded, select("pen") does nothing and injected strokes become
    # whatever tool xochitl has active.
    try:
        from riddle.device import taps

        known = taps.load()
    except Exception as exc:  # noqa: BLE001 - a broken taps file must not hide here
        known = {}
        out.append(Result(FAIL, "assets", "taps.json", f"unreadable: {exc}"))
    if known.get("pen"):
        out.append(Result(OK, "assets", "pen tap", f"{len(known['pen'])} recorded"))
    else:
        out.append(
            Result(
                FAIL, "assets", "pen tap",
                "no pen tap recorded, so the diary cannot select the pen and its "
                "writing will become whatever tool is active",
                "riddle taps learn pen --yes",
            )
        )
    return out


def check_store() -> list[Result]:
    import sqlite3

    cfg = config.get()
    if not cfg.db.is_file():
        return [Result(WARN, "store", "database", f"{cfg.db} does not exist yet")]
    try:
        conn = sqlite3.connect(f"file:{cfg.db}?mode=ro", uri=True)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        counts = {}
        for table in ("sessions", "events", "intents"):
            if table in tables:
                counts[table] = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        conn.close()
    except sqlite3.Error as exc:
        return [Result(FAIL, "store", "database", str(exc), "delete it; it is disposable")]
    out = [Result(OK, "store", "database", str(cfg.db))]
    out.append(Result(OK if mode == "wal" else WARN, "store", "journal", mode))
    missing = {"sessions", "events", "strokes", "turns", "intents"} - tables
    if missing:
        out.append(Result(WARN, "store", "schema", f"missing {', '.join(sorted(missing))}"))
    out.append(
        Result(OK, "store", "rows",
               ", ".join(f"{k} {v}" for k, v in counts.items()) or "empty")
    )
    return out


def check_asr() -> list[Result]:
    cfg = config.get()
    if cfg.asr_model.is_file():
        size = cfg.asr_model.stat().st_size // (1024 * 1024)
        return [Result(OK, "asr", "model", f"{paths.relative(cfg.asr_model)} ({size}M)")]
    return [
        Result(
            WARN, "asr", "model", f"none at {cfg.asr_model}",
            "the page runs without one; the microphone is simply off",
        )
    ]


def check_web() -> list[Result]:
    cfg = config.get()
    src = paths.ROOT / "apps" / "web" / "src"
    out = []
    if not (paths.ROOT / "apps" / "web" / "node_modules").is_dir():
        out.append(Result(WARN, "web", "deps", "not installed", "riddle web install"))
    index = cfg.web_dir / "index.html"
    if not index.is_file():
        out.append(
            Result(WARN, "web", "build", "not built, so the server serves a stub page",
                   "riddle web build")
        )
        return out
    newest = max((f.stat().st_mtime for f in src.rglob("*") if f.is_file()), default=0)
    if newest > index.stat().st_mtime:
        out.append(Result(WARN, "web", "build", "older than src/", "riddle web build"))
    else:
        out.append(Result(OK, "web", "build", paths.relative(cfg.web_dir)))
    return out


def check_services() -> list[Result]:
    from riddle import process, tailnet

    cfg = config.get()
    out = []
    for service in (process.DIARY, process.VOICE):
        pid = process.alive(service)
        if pid:
            out.append(Result(OK, "services", service.name, f"{service.verb} (pid {pid})"))
        elif service.pidfile.exists():
            out.append(Result(WARN, "services", service.name, "stale pidfile",
                              f"riddle {service.name} status clears it"))
        else:
            out.append(Result(OK, "services", service.name, "not running"))
    if tailnet.port_open(cfg.web_host, cfg.web_port) and not process.alive(process.VOICE):
        out.append(
            Result(WARN, "services", "port",
                   f"something else is on {cfg.web_host}:{cfg.web_port}")
        )
    orphans = _orphan_agents()
    if orphans:
        out.append(
            Result(WARN, "services", "agent",
                   f"{orphans} ssh connection(s) to the agent with no service behind them",
                   "kill them, or they keep the digitizer")
        )
    return out


def _orphan_agents() -> int:
    from riddle import process

    try:
        done = subprocess.run(["pgrep", "-f", "riddled"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return 0
    pids = [p for p in done.stdout.split() if p.isdigit()]
    if not pids:
        return 0
    if process.alive(process.DIARY):
        return 0
    return len(pids)


def check_tablet(quick: bool = False) -> list[Result]:
    if quick:
        return []
    from riddle import probe

    cfg = config.get()
    out = []
    if not probe.reachable(cfg.ssh_host):
        return [
            Result(FAIL, "tablet", "route", f"{cfg.ssh_host} does not answer",
                   "riddle link to find one that does")
        ]
    out.append(Result(OK, "tablet", "route", cfg.ssh_host))
    timing = probe.agent_latency(cfg.ssh_host)
    if isinstance(timing, tuple):
        median, worst = timing
        out.append(Result(OK, "tablet", "agent", f"{median:.0f} ms median, {worst:.0f} ms worst"))
    else:
        out.append(Result(FAIL, "tablet", "agent", str(timing), "riddle device build"))
    local = paths.BUILD / "riddled"
    if local.is_file():
        try:
            done = subprocess.run(
                ["ssh", cfg.ssh_host, f"stat -c %s {cfg.agent}"],
                capture_output=True, text=True, timeout=20,
            )
            remote_size = int(done.stdout.strip() or 0)
        except (OSError, subprocess.SubprocessError, ValueError):
            remote_size = 0
        if remote_size and remote_size != local.stat().st_size:
            out.append(
                Result(WARN, "tablet", "agent build",
                       "the tablet's agent differs from your local build",
                       "riddle device build")
            )
    return out


GROUPS = ("tools", "python", "config", "assets", "store", "asr", "web", "services", "tablet")


def run_checks(only: str | None = None, quick: bool = False) -> list[Result]:
    checks = {
        "tools": check_tools,
        "python": check_python,
        "config": check_config,
        "assets": check_assets,
        "store": check_store,
        "asr": check_asr,
        "web": check_web,
        "services": check_services,
        "tablet": lambda: check_tablet(quick),
    }
    results: list[Result] = []
    for name in GROUPS:
        if only and name != only:
            continue
        if quick and name == "tablet":
            continue
        results.extend(checks[name]())
    return results


def report(results: list[Result]) -> str:
    lines: list[str] = []
    group = None
    width = max((len(r.name) for r in results), default=10)
    for result in results:
        if result.group != group:
            group = result.group
            lines.append("")
            lines.append(f"  {group}")
        detail = result.detail
        lines.append(f"  {result.status:<5} {result.name:<{width}}  {detail}".rstrip())
        if result.fix and result.status != OK:
            lines.append(f"  {'':<5} {'':<{width}}  -> {result.fix}")
    return "\n".join(lines).strip("\n")
