#!/usr/bin/env python3
"""Find the tablet and say which way of reaching it is worth using.

The diary does not care whether it is talking over the usb cable or over wifi:
the agent performs every delay itself, so a slower link shifts a stroke rather
than distorting it. What you do want to know before switching is whether the
tablet answers at all on wifi, and how much round trip you are buying.

This draws nothing, so it needs no --yes.

    link.py                 # probe usb, wifi and mDNS
    link.py 192.168.1.42    # probe that address too
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from device import SSH_OPTIONS

USB = "10.11.99.1"
MDNS = "remarkable.local"
ROUNDS = 5


def resolve(host: str) -> str:
    """The address an ssh alias points at, so the tcp probe can reach it too."""
    try:
        out = subprocess.run(
            ["ssh", "-G", host], capture_output=True, text=True, timeout=10
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return host
    for line in out.splitlines():
        if line.startswith("hostname "):
            return line.split(None, 1)[1].strip()
    return host


def reachable(host: str, port: int = 22, timeout: float = 2.0) -> float | None:
    """Seconds to open a TCP connection to the ssh port, or None."""
    started = time.monotonic()
    try:
        with socket.create_connection((resolve(host), port), timeout=timeout):
            return time.monotonic() - started
    except OSError:
        return None


def agent_latency(host: str) -> tuple[float, float] | str:
    """Median and worst PING/PONG round trip through the agent, in ms.

    This is the number that matters: it covers the network, sshd, and the
    agent's own stdin handling, which is the whole path a drawing command
    takes. On failure this returns ssh's own complaint rather than None,
    because the usual cause is authentication -- a bare address does not pick
    up the IdentityFile that an ssh alias would have supplied -- and "no
    answer" sends you looking at the wrong thing entirely.
    """
    agent = os.environ.get("RIDDLE_AGENT", "/home/root/riddle/riddled")
    try:
        proc = subprocess.Popen(
            ["ssh", *SSH_OPTIONS, "-o", "BatchMode=yes", host, agent],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        return str(exc)

    def complaint() -> str:
        noise = ("Warning: Permanently added", "Pseudo-terminal")
        for line in (proc.stderr.read() or "").splitlines():
            if line.strip() and not line.startswith(noise):
                return line.strip()
        return "no answer from the agent"

    samples: list[float] = []
    try:
        # Wait for the agent to announce itself before timing anything.
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                return complaint()
            if line.startswith("READY"):
                break
        else:
            return "agent never said READY"

        for _ in range(ROUNDS):
            started = time.monotonic()
            try:
                proc.stdin.write("PING\n")
                proc.stdin.flush()
            except (BrokenPipeError, ValueError):
                return complaint()
            while True:
                line = proc.stdout.readline()
                if not line:
                    return complaint()
                if line.startswith("PONG"):
                    break
            samples.append((time.monotonic() - started) * 1000)
    finally:
        # Close the pipes explicitly: left to the garbage collector they are
        # finalised after the process is gone and print a BrokenPipeError
        # traceback over the results.
        if proc.poll() is None:
            try:
                proc.stdin.write("QUIT\n")
                proc.stdin.flush()
            except (BrokenPipeError, ValueError, OSError):
                pass
        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            try:
                pipe.close()
            except (BrokenPipeError, ValueError, OSError):
                pass
        proc.terminate()
        proc.wait(timeout=5)

    samples.sort()
    return samples[len(samples) // 2], samples[-1]


def probe(label: str, host: str) -> bool:
    opened = reachable(host)
    if opened is None:
        print(f"{label:22} {host:22} unreachable")
        return False

    latency = agent_latency(host)
    if isinstance(latency, str):
        print(
            f"{label:22} {host:22} ssh open ({opened * 1000:.0f} ms), "
            f"but: {latency}"
        )
        return False

    median, worst = latency
    print(
        f"{label:22} {host:22} agent round trip "
        f"{median:.0f} ms median, {worst:.0f} ms worst"
    )
    return True


def main() -> None:
    # Aliases first: an entry in ~/.ssh/config carries the key and user, which
    # a bare address does not, so a raw ip can fail here purely on auth.
    targets = [
        ("alias rm2", "rm2"),
        ("alias rm2-wifi", "rm2-wifi"),
        ("usb cable", USB),
        ("mDNS", MDNS),
    ]

    wifi = os.environ.get("RM2_WIFI_HOST")
    if wifi:
        targets.append(("RM2_WIFI_HOST", wifi))
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            targets.append(("argument", arg))

    print(f"probing {len(targets)} routes to the tablet\n")
    working = [host for label, host in targets if probe(label, host)]

    print()
    if not working:
        print(
            "nothing answered. check the tablet is awake, and that wifi is on\n"
            "and ssh is enabled under Settings > General > Storage"
        )
        return

    print(f"usable: {', '.join(working)}")
    best = working[0]
    print(f"\nto use it:  export RM2_SSH_HOST={best}")
    print("or add it to ~/.ssh/config so the alias 'rm2' points there.")


if __name__ == "__main__":
    main()
