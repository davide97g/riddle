"""The two halves as services that survive a reboot, on whatever the server is.

On the author's box the units were written by hand, once, and that was fine
for one box. For anybody else's server the same two files have to come out of
the checkout they are pointing at, so they are generated here: systemd user
units on Linux, launch agents on a Mac. `riddle.process.manager` is what reads
them back, so the page's start and stop go through the supervisor rather than
spawning a second loop beside it.

What is the same on both, and why:

- The voice half before the loop. The page is meant to be up first, so a loop
  that cannot reach the tablet has somewhere to say so.
- The loop's whole process group goes when it stops. It owns an ssh
  subprocess holding the agent's stdin, and killing only the python leaves
  that ssh holding the digitizer, so the next start cannot have it. systemd
  says that with `KillMode=control-group`; launchd does it by default unless
  told `AbandonProcessGroup`.
- A PATH written into the file. A supervisor's environment is not a login
  shell's: `parakeet-cli`, `bun` and `ssh` have to be found by name, and
  where each one lives is worked out now, while a shell that has them is
  running this.
- Restart on any exit, five seconds apart. A crash is not clean and cannot
  be (`docs/deploy.md`): the next start refuses while the dead loop's beat
  is fresh, and comes up by itself within a minute.

Nothing here touches the tablet.
"""

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from riddle import paths, process

DESCRIPTION = {
    "voice": "riddle: the page you speak into",
    "diary": "riddle: the loop that watches the page and answers on it",
}

# Asked for by name, so the directories they are in go on the PATH.
TOOLS = ("ssh", "parakeet-cli", "bun", "tailscale", "zig")


def _python() -> Path:
    """The venv's interpreter: the one running this, with riddle installed."""
    venv = paths.ROOT / ".venv" / "bin" / "python"
    return venv if venv.exists() else Path(sys.executable)


def search_path() -> str:
    found: list[str] = []
    home = Path.home()
    for name in TOOLS:
        where = shutil.which(name)
        if where:
            found.append(str(Path(where).parent))
    found += [
        str(home / ".local" / "bin"),
        str(home / ".bun" / "bin"),
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]
    out: list[str] = []
    for item in found:
        if item not in out:
            out.append(item)
    return ":".join(out)


# --- systemd ------------------------------------------------------------


def systemd_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "systemd" / "user"


def systemd_unit(name: str) -> str:
    service = process.SERVICES[name]
    lines = ["[Unit]", f"Description={DESCRIPTION[name]}"]
    if name == "voice":
        lines += ["Before=riddle-diary.service"]
    else:
        lines += ["After=riddle-voice.service", "Wants=riddle-voice.service"]
    lines += [
        "",
        "[Service]",
        "Type=simple",
        f"WorkingDirectory={paths.ROOT}",
        f"Environment=PATH={search_path()}",
    ]
    if name == "diary":
        lines += [
            "# It owns an ssh pipe to the tablet; killing only the python leaves",
            "# that ssh holding the digitizer, so the whole control group goes.",
            "KillMode=control-group",
        ]
    lines += [
        f"ExecStart={_python()} -u -m {service.module}",
        "Restart=always",
        "RestartSec=5",
        "",
        "[Install]",
        "WantedBy=default.target",
        "",
    ]
    return "# Written by `riddle service install`; rerun it rather than editing.\n" + "\n".join(lines)


def _systemctl(*argv: str) -> int:
    done = subprocess.run(["systemctl", "--user", *argv])
    return done.returncode


def _install_systemd(names: list[str], start: bool) -> int:
    where = systemd_dir()
    where.mkdir(parents=True, exist_ok=True)
    for name in names:
        path = where / f"{process.unit(process.SERVICES[name])}.service"
        path.write_text(systemd_unit(name))
        print(f"wrote {path}")
    code = _systemctl("daemon-reload")
    if code:
        return code
    units = [process.unit(process.SERVICES[n]) for n in names]
    code = _systemctl("enable", *(["--now"] if start else []), *units)
    if code:
        return code
    # Without lingering a user's units stop at logout and do not start at
    # boot, which on a box nobody logs in to means never.
    user = os.environ.get("USER", "")
    linger = subprocess.run(["loginctl", "enable-linger", user], capture_output=True, text=True)
    if linger.returncode:
        print(f"could not turn on lingering ({linger.stderr.strip() or 'loginctl failed'}).")
        print(f"  run once: sudo loginctl enable-linger {user}")
        print("  or the halves stop when you log out and do not start at boot.")
    return 0


def _uninstall_systemd(names: list[str]) -> int:
    units = [process.unit(process.SERVICES[n]) for n in names]
    _systemctl("disable", "--now", *units)
    for unit in units:
        path = systemd_dir() / f"{unit}.service"
        if path.exists():
            path.unlink()
            print(f"removed {path}")
    _systemctl("daemon-reload")
    return 0


# --- launchd ------------------------------------------------------------


def launchd_plist(name: str) -> bytes:
    service = process.SERVICES[name]
    body = {
        "Label": process.label(name),
        "ProgramArguments": [str(_python()), "-u", "-m", service.module],
        "WorkingDirectory": str(paths.ROOT),
        "EnvironmentVariables": {"PATH": search_path()},
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 5,
        # The same files `riddle diary log` reads when it runs them itself.
        "StandardOutPath": str(service.logfile),
        "StandardErrorPath": str(service.logfile),
    }
    return plistlib.dumps(body)


def _install_launchd(names: list[str], start: bool) -> int:
    paths.ensure()
    domain = f"gui/{os.getuid()}"
    for name in names:
        path = process.plist(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        # A loaded agent keeps the old file's arguments until it is booted out.
        subprocess.run(["launchctl", "bootout", f"{domain}/{process.label(name)}"],
                       capture_output=True)
        path.write_bytes(launchd_plist(name))
        print(f"wrote {path}")
        if start:
            done = subprocess.run(["launchctl", "bootstrap", domain, str(path)],
                                  capture_output=True, text=True)
            if done.returncode:
                print(f"launchctl bootstrap {path.name}: {done.stderr.strip()}")
                return done.returncode
    return 0


def _uninstall_launchd(names: list[str]) -> int:
    domain = f"gui/{os.getuid()}"
    for name in names:
        subprocess.run(["launchctl", "bootout", f"{domain}/{process.label(name)}"],
                       capture_output=True)
        path = process.plist(name)
        if path.exists():
            path.unlink()
            print(f"removed {path}")
    return 0


# --- the verbs ----------------------------------------------------------


def kind() -> str | None:
    if sys.platform == "darwin":
        return "launchd"
    if sys.platform.startswith("linux") and shutil.which("systemctl"):
        return "systemd"
    return None


def install(names: list[str], *, start: bool = True) -> int:
    which = kind()
    if which is None:
        print("no service manager here that this knows: run `riddle start` instead,")
        print("or the container in deploy/docker.")
        return 1
    # A half already running with a pidfile is a second loop the moment the
    # supervisor starts its own, and two ssh pipes into one digitizer.
    for name in names:
        service = process.SERVICES[name]
        if process.alive(service) is not None:
            print(f"stopping the {name} half riddle started itself first")
            process.stop(service)
    process.manager.cache_clear()
    if which == "launchd":
        code = _install_launchd(names, start)
    else:
        code = _install_systemd(names, start)
    if not code:
        print(f"{' and '.join(names)} now run under {which}"
              + ("" if start else "; not started"))
    return code


def uninstall(names: list[str]) -> int:
    which = kind()
    if which == "launchd":
        code = _uninstall_launchd(names)
    elif which == "systemd":
        code = _uninstall_systemd(names)
    else:
        print("nothing installed: no service manager here")
        return 1
    process.manager.cache_clear()
    return code


def show(name: str) -> str:
    """What `install` would write for one half, for reading before trusting."""
    if kind() == "launchd":
        return launchd_plist(name).decode()
    return systemd_unit(name)
