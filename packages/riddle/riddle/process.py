"""Running the two long-lived halves in the background.

This was the same forty lines of bash twice, once in diary.sh and once in
voice.sh, and the two had already started to drift. Three things are
different here on purpose:

The child gets its own session (`start_new_session`), which is what makes it
survive the terminal closing and ignore a Ctrl-C meant for the shell. But
unlike a double fork it leaves us holding a handle, so the settle window can
ask the child whether it actually died instead of sleeping two seconds and
guessing.

Stopping signals the process *group*. The loop owns an ssh subprocess
holding the agent's stdin; killing only the Python left that ssh alive, and
the next start then could not have the digitizer. The old script's own
comment described this and did not fix it.

And the log rotates one deep rather than being truncated, because
overwriting it at startup destroys the evidence of the crash you are about
to investigate.
"""

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from riddle import paths


@dataclass(frozen=True)
class Service:
    name: str
    module: str
    verb: str          # the word `status` prints when it is up
    settle_s: float    # how long to watch a new child before believing it

    @property
    def pidfile(self) -> Path:
        return paths.RUN / f"{self.name}.pid"

    @property
    def logfile(self) -> Path:
        return paths.LOG / f"{self.name}.log"


DIARY = Service("diary", "riddle.apps.diary", "listening", 3.0)
VOICE = Service("voice", "riddle.apps.voice", "up", 2.0)
SERVICES = {s.name: s for s in (DIARY, VOICE)}


def unit(service: Service) -> str:
    """The systemd user unit that runs this half on the box."""
    return f"riddle-{service.name}"


def _systemctl(*argv: str, timeout: float = 20.0):
    try:
        return subprocess.run(
            ["systemctl", "--user", *argv],
            capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None


@lru_cache(maxsize=None)
def manager(name: str) -> str:
    """Who is expected to run this half *here*: `systemd`, or `here`.

    On the box both halves are user units. A start that spawned a child
    beside the unit would put two ssh pipes into one digitizer, and a stop
    that went looking for a pidfile would find none and report success over
    a service that is still answering. So anything that wants to bring a
    half up or down asks this first, and then asks whoever actually holds it
    -- which is what `elsewhere()` has always said to do.

    Memoised: a unit file does not appear halfway through a process, and the
    page asks about the loop four times a second.
    """
    done = _systemctl("show", f"riddle-{name}", "--property=LoadState", "--value")
    if done is not None and done.returncode == 0 and done.stdout.strip() == "loaded":
        return "systemd"
    return "here"


def begin(service: Service) -> tuple[int, str]:
    """Bring a half up the way this machine runs it. `(code, what to say)`.

    The pair of this and `end` is what the page drives. They return a line
    rather than printing one, because on the other end of them is a browser
    and not a terminal.
    """
    if manager(service.name) == "systemd":
        done = _systemctl("start", unit(service), timeout=60.0)
        if done is None:
            return 1, "systemctl is not answering"
        if done.returncode:
            return done.returncode, done.stderr.strip() or f"{unit(service)} did not start"
        return 0, f"asked systemd for {unit(service)}"
    code = start(service)
    if code:
        return code, tail(service.logfile, 8) or "it did not come up"
    return 0, f"{service.verb} (pid {alive(service)})"


def end(service: Service, *, timeout: float = 6.0) -> tuple[int, str]:
    """Take a half down the way this machine runs it. `(code, what to say)`."""
    if manager(service.name) == "systemd":
        done = _systemctl("stop", unit(service), timeout=max(30.0, timeout))
        if done is None:
            return 1, "systemctl is not answering"
        if done.returncode:
            return done.returncode, done.stderr.strip() or f"{unit(service)} did not stop"
        # The unit's own SIGTERM handler clears the beat on the way out, but
        # a kill after the timeout does not, and the next start would then
        # refuse for the rest of the stale window.
        forget_heartbeat(service)
        return 0, f"asked systemd to stop {unit(service)}"
    stop(service, timeout=timeout)
    return 0, "stopped"


def _read_pidfile(service: Service) -> int | None:
    try:
        first = service.pidfile.read_text().split("\n")[0].strip()
        return int(first)
    except (OSError, ValueError):
        return None


def _command_of(pid: int) -> str:
    try:
        done = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip()


def alive(service: Service) -> int | None:
    """The pid, if that pid is really this service.

    Three checks, not one. A pidfile whose process has died and whose number
    has been handed to something else would otherwise read as running -- and
    `stop` would then signal a stranger.
    """
    pid = _read_pidfile(service)
    if pid is None:
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    if service.module not in _command_of(pid):
        return None
    return pid


def elsewhere(service: Service) -> int | None:
    """A process running this service that no pidfile here claims.

    systemd is the usual answer. On the box the two halves are user units,
    and a unit keeps no pidfile in `var/run`, so everything that reads one --
    `status`, `doctor`, the orphan-ssh check -- would otherwise report a
    machine as idle while it is plainly answering.

    It is deliberately only *reported*, never acted on: `stop` still refuses
    to signal anything it did not start, because the supervisor that did is
    the thing that should be asked.
    """
    if alive(service) is not None:
        return None
    try:
        done = subprocess.run(
            # `--`, because the pattern starts with a dash and pgrep would
            # otherwise read `-m` as one of its own flags and match nothing.
            ["pgrep", "-f", "--", f"-m {service.module}"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for token in done.stdout.split():
        if token.isdigit() and int(token) != os.getpid():
            return int(token)
    return None


def clear_stale(service: Service) -> bool:
    """Remove a pidfile that no longer names this service."""
    if service.pidfile.exists() and alive(service) is None:
        service.pidfile.unlink(missing_ok=True)
        return True
    return False


def tail(path: Path, lines: int) -> str:
    if not path.is_file():
        return ""
    return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])


def _rotate(path: Path) -> None:
    if path.is_file() and path.stat().st_size:
        os.replace(path, path.with_suffix(path.suffix + ".1"))


def start(service: Service, *, append_log: bool = False, extra_env: dict | None = None) -> int:
    """Bring a service up in the background. Returns an exit code."""
    paths.ensure()
    running = alive(service)
    if running:
        print(f"already up (pid {running})")
        return 0
    clear_stale(service)
    if not append_log:
        _rotate(service.logfile)

    env = {**os.environ, **(extra_env or {})}
    log = open(service.logfile, "ab", buffering=0)
    try:
        child = subprocess.Popen(
            [sys.executable, "-m", service.module],
            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            start_new_session=True, close_fds=True, cwd=paths.ROOT, env=env,
        )
    finally:
        log.close()

    deadline = time.monotonic() + service.settle_s
    while time.monotonic() < deadline:
        if child.poll() is not None:
            break
        time.sleep(0.1)

    if child.poll() is not None:
        service.pidfile.unlink(missing_ok=True)
        print(f"failed to start (exit {child.returncode}):", file=sys.stderr)
        print(tail(service.logfile, 15), file=sys.stderr)
        return 1

    service.pidfile.write_text(f"{child.pid}\npython -m {service.module}\n")
    print(f"{service.verb} (pid {child.pid}), log: {paths.relative(service.logfile)}")
    last = tail(service.logfile, 5)
    if last:
        print(last)
    return 0


def forget_heartbeat(service: Service) -> None:
    """Say in the store that this half is gone.

    Liveness there is a heartbeat, not a pidfile, and a beat outlives the
    process that made it by a minute. The loop reads the loop's beat when it
    starts and refuses if another one looks alive, so without this a diary
    stopped on purpose blocks the next one for the rest of the stale window.

    `riddle dev` clears it for the same reason on every reload, which is why
    this is not private.

    Best effort on purpose: a missing, locked or simply absent store is not a
    reason a stop fails.
    """
    try:
        from riddle import config
        from riddle.store import Store

        store = Store.attach(config.get().db)
        if store is None:
            return
        try:
            store.gone("loop" if service is DIARY else "voice")
        finally:
            store.conn.close()
    except Exception as exc:  # noqa: BLE001 - never fail a stop over bookkeeping
        print(f"could not clear the heartbeat: {exc}", file=sys.stderr)


def stop(service: Service, *, timeout: float = 6.0) -> int:
    pid = alive(service)
    if pid is None:
        # Whether or not a process was found, the beat may still be there:
        # this is also the path `riddle start` takes over a half that died
        # seconds ago.
        forget_heartbeat(service)
        if clear_stale(service):
            print("not running (cleared a stale pidfile)")
        else:
            print("not running")
        return 0

    group = os.getpgid(pid)
    os.killpg(group, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if alive(service) is None:
            break
        time.sleep(0.1)
    if alive(service) is not None:
        os.killpg(group, signal.SIGKILL)
        time.sleep(0.3)
    service.pidfile.unlink(missing_ok=True)
    forget_heartbeat(service)
    print("stopped")
    return 0


def status(service: Service, *, lines: int = 3) -> int:
    pid = alive(service)
    if pid is None:
        other = elsewhere(service)
        if other is not None:
            print(f"{service.verb} (pid {other}), started by something else")
            print("systemctl --user status riddle-" + service.name)
            return 0
        if clear_stale(service):
            print("not running (cleared a stale pidfile)")
        else:
            print("not running")
        return 1
    print(f"{service.verb} (pid {pid})")
    last = tail(service.logfile, lines)
    if last:
        print(last)
    return 0


def log(service: Service, *, lines: int = 40, follow: bool = False) -> int:
    if not service.logfile.is_file():
        print("no log yet")
        return 1
    if not follow:
        print(tail(service.logfile, lines))
        return 0
    with service.logfile.open("r", errors="replace") as handle:
        handle.seek(0, os.SEEK_END)
        try:
            while True:
                line = handle.readline()
                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                else:
                    time.sleep(0.2)
        except KeyboardInterrupt:
            return 0


def run_foreground(service: Service) -> int:
    """Run in this terminal instead, the way run.sh used to."""
    paths.ensure()
    import asyncio
    import importlib
    import inspect

    module = importlib.import_module(service.module)
    try:
        result = module.main()
        if inspect.isawaitable(result):
            result = asyncio.run(result)
    except KeyboardInterrupt:
        return 0
    return int(result or 0)
