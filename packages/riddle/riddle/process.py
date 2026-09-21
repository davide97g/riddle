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
