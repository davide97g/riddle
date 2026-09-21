"""`riddle dev`: `riddle start`, but nothing has to be restarted by hand.

The client already reloads itself -- vite has done that since the beginning
-- so this exists for the other three quarters of the machine: the loop, the
voice server, and the fact that the two of them plus the dev server are three
terminals to keep alive and one order to remember.

So the halves run here as children rather than in the background, their
output is interleaved into this terminal with a tag in front of each line,
and a change under `packages/riddle/riddle` stops both and brings both back.

Three things it is careful about, all of them borrowed from `riddle.process`
because they are the same hazards:

Each child gets its own session, and a reload signals the process *group*.
The loop owns an ssh subprocess holding the agent's stdin; killing only the
python leaves that ssh alive, and the next loop then cannot have the
digitizer.

A reload clears the heartbeat as well as the pidfile. Liveness in the store
is a beat that outlives its process by a minute, and the loop refuses to
start while another one looks alive -- so without this the *second* copy of
the loop would refuse for the rest of the stale window, once per save.

And the pidfiles are written, so `riddle diary status` tells the truth while
this is running and a stray `riddle start` stops these children rather than
racing a second ssh pipe into the same digitizer.

An interrupted turn is not a hazard: the loop gives up any intent it finds
left `running` when it starts, which is the same recovery a crash gets.
"""

import os
import shlex
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from riddle import paths, process, toolchain

POLL_S = 0.4        # how often the tree is compared against itself
SETTLE_S = 0.3      # an editor writing four files should be one reload

TAGS = {"diary": "35", "voice": "36", "web": "33"}

_SPEAKING = threading.Lock()


def _say(name: str, line: str) -> None:
    """One line out, from whichever thread has it."""
    colour = TAGS.get(name)
    tag = f"\033[{colour}m{name:>5}\033[0m" if colour and sys.stdout.isatty() else f"{name:>5}"
    with _SPEAKING:
        print(f"{tag} | {line}", flush=True)


class Child:
    """One supervised process, and the pidfile it may stand behind."""

    def __init__(self, name: str, argv: list[str], cwd: Path, env=None, service=None):
        self.name = name
        self.argv = argv
        self.cwd = cwd
        self.env = env
        self.service = service
        self.popen: subprocess.Popen | None = None

    def start(self) -> None:
        self.popen = subprocess.Popen(
            self.argv,
            cwd=self.cwd, env=self.env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            start_new_session=True, close_fds=True,
            text=True, errors="replace", bufsize=1,
        )
        threading.Thread(target=self._pump, args=(self.popen,), daemon=True).start()
        if self.service is not None:
            self.service.pidfile.write_text(f"{self.popen.pid}\n{shlex.join(self.argv)}\n")
        _say(self.name, f"pid {self.popen.pid}")

    def _pump(self, popen: subprocess.Popen) -> None:
        assert popen.stdout is not None
        for line in popen.stdout:
            _say(self.name, line.rstrip("\n"))

    def reap(self) -> None:
        """Notice a child that died on its own, and say so once."""
        if self.popen is None or self.popen.poll() is None:
            return
        code = self.popen.returncode
        self.popen = None
        self._forget()
        _say(self.name, f"exited ({code}); it will come back on the next change")

    def stop(self, timeout: float = 6.0) -> None:
        popen, self.popen = self.popen, None
        if popen is not None and popen.poll() is None:
            self._signal(popen, signal.SIGTERM)
            try:
                popen.wait(timeout)
            except subprocess.TimeoutExpired:
                self._signal(popen, signal.SIGKILL)
                try:
                    popen.wait(2.0)
                except subprocess.TimeoutExpired:
                    pass
        self._forget()

    @staticmethod
    def _signal(popen: subprocess.Popen, sig: int) -> None:
        try:
            os.killpg(os.getpgid(popen.pid), sig)
        except (ProcessLookupError, PermissionError):
            pass

    def _forget(self) -> None:
        if self.service is None:
            return
        self.service.pidfile.unlink(missing_ok=True)
        process.forget_heartbeat(self.service)


def _sources() -> dict[Path, int]:
    """Every python file the halves import, plus the settings they read.

    Modification times rather than hashes: an editor that writes a file
    unchanged costs one reload, which is cheaper than stat-and-read on every
    poll. `__pycache__` is skipped because it changes as a *result* of the
    reload and would otherwise start the next one.
    """
    seen: dict[Path, int] = {}
    for path in paths.PACKAGE.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            seen[path] = path.stat().st_mtime_ns
        except OSError:      # deleted between the walk and the stat
            continue
    dotenv = paths.ROOT / ".env"
    try:
        seen[dotenv] = dotenv.stat().st_mtime_ns
    except OSError:
        pass
    return seen


def _changed(before: dict[Path, int], after: dict[Path, int]) -> list[str]:
    names = {p for p in set(before) | set(after) if before.get(p) != after.get(p)}
    return sorted(paths.relative(p) for p in names)


def _reload(halves: list[Child], timeout: float) -> None:
    """Both down, then both up, in the order `riddle start` uses.

    Both are stopped before either is started for the reason a half-running
    machine is confusing, and because a second loop will not start while the
    first is still beating. Up again: the page first, the pen second, so the
    loop's failure has somewhere to show.
    """
    for child in reversed(halves):
        child.stop(timeout)
    for child in halves:
        child.start()


def run(*, timeout: float = 6.0, web: bool = True, tailnet: bool = False) -> int:
    paths.ensure()

    if web and not toolchain.have_bun():
        print(toolchain.MISSING)
        return 1

    for service in (process.DIARY, process.VOICE):
        print(f"-- {service.name}")
        process.stop(service, timeout=timeout)

    halves = [
        Child(service.name, [sys.executable, "-u", "-m", service.module],
              paths.ROOT, service=service)
        for service in (process.VOICE, process.DIARY)
    ]
    children = list(halves)
    if web:
        children.insert(0, Child(
            "web", ["bun", "run", "dev"], toolchain.WHERE,
            env=toolchain.env(tailnet=tailnet),
        ))

    print("\n-- dev: saving a .py file under packages/riddle restarts both halves")
    if web:
        print("   the page is vite's own address, not the python port")
    print("   ctrl-c stops everything\n")

    for child in children:
        child.start()

    seen = _sources()
    try:
        while True:
            time.sleep(POLL_S)
            for child in children:
                child.reap()
            now = _sources()
            if now == seen:
                continue
            time.sleep(SETTLE_S)          # let a multi-file save finish
            now = _sources()
            touched = _changed(seen, now)
            seen = now
            print()
            _say("dev", f"changed: {', '.join(touched[:3])}"
                        + (f" (+{len(touched) - 3} more)" if len(touched) > 3 else ""))
            _reload(halves, timeout)
    except KeyboardInterrupt:
        print()
    finally:
        for child in reversed(children):
            child.stop(timeout)
        print("-- dev: everything is down")
    return 0
