"""Cross-compile the on-tablet agent and put it on the tablet.

zig is the cross-compiler because it ships the whole toolchain in one binary
and can target arm-linux-musleabihf without a sysroot; the result is static,
so nothing on the tablet has to provide a libc that matches.

This used to be a shell script that said `ssh rm2` three times in literal
text, which meant that with RM2_SSH_HOST pointing at wifi the loop talked to
one route and the deploy went down another.
"""

import shutil
import subprocess

from riddle import config, paths
from riddle.device.ssh import BASE, REMOTE_AGENT

SOURCE = "device/riddled.c"
TARGET = "arm-linux-musleabihf"


def compile_agent(out) -> int:
    if not shutil.which("zig"):
        print("zig is not installed: brew install zig")
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(
        [
            "zig", "cc",
            "-target", TARGET,
            "-static",
            "-Os",
            "-o", str(out),
            str(paths.ROOT / SOURCE),
        ],
        cwd=paths.ROOT,
    )
    return done.returncode


def deploy(out, host: str) -> int:
    remote_dir = REMOTE_AGENT.rsplit("/", 1)[0]
    steps = [
        ["ssh", *BASE, host, f"mkdir -p {remote_dir}"],
        ["scp", *BASE, "-q", str(out), f"{host}:{REMOTE_AGENT}"],
        ["ssh", *BASE, host, f"chmod +x {REMOTE_AGENT}"],
    ]
    for step in steps:
        done = subprocess.run(step)
        if done.returncode:
            return done.returncode
    return 0


def run(args) -> int:
    host = args.host or config.get().ssh_host
    out = args.out or (paths.BUILD / "riddled")

    code = compile_agent(out)
    if code:
        return code
    size = out.stat().st_size // 1024
    print(f"built {paths.relative(out)} ({size}K)")

    if args.no_deploy:
        return 0
    code = deploy(out, host)
    if code:
        return code
    print(f"deployed to {host}:{REMOTE_AGENT}")
    return 0
