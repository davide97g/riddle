"""Putting a real certificate in front of the page.

A browser will not hand a page the microphone unless it is a secure context,
and a lan address over plain http is not one. That is the whole reason this
module exists: `tailscale serve` terminates TLS with the certificate the
tailnet already holds for this machine's name and proxies to loopback, so
the server itself never grows an ssl import and never has to bind anything
but 127.0.0.1.

The shell version scraped the machine's name out of `tailscale status
--json` with two `sed` passes -- one for the host label, one for the tailnet
suffix -- and ran the command twice to do it, because sed cannot navigate an
object. The field it was reassembling is already there, whole.
"""

import json
import socket
import subprocess


class TailscaleError(RuntimeError):
    pass


def _run(args: list[str], timeout: int = 15) -> str:
    try:
        done = subprocess.run(
            ["tailscale", *args], capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError:
        raise TailscaleError("tailscale is not installed") from None
    except subprocess.SubprocessError as exc:
        raise TailscaleError(f"tailscale {' '.join(args)} failed: {exc}") from None
    if done.returncode:
        raise TailscaleError((done.stderr or done.stdout).strip())
    return done.stdout


def status() -> dict:
    try:
        return json.loads(_run(["status", "--json"]))
    except json.JSONDecodeError:
        raise TailscaleError("tailscale status did not return json") from None


def self_dns_name() -> str:
    """This machine's fully qualified tailnet name."""
    data = status()
    name = (data.get("Self") or {}).get("DNSName", "").rstrip(".")
    if name:
        return name
    host = (data.get("Self") or {}).get("HostName", "")
    suffix = data.get("MagicDNSSuffix", "")
    if host and suffix:
        return f"{host}.{suffix}"
    raise TailscaleError("tailscale is not logged in, or has no MagicDNS name")


def port_open(host: str, port: int, timeout: float = 0.1) -> bool:
    """Is something actually listening? A pidfile can say yes and be wrong."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def serve(port: int) -> str:
    """Proxy https on the tailnet name to loopback:port. Returns the url."""
    _run(["serve", "--bg", str(port)], timeout=60)
    return f"https://{self_dns_name()}/"


def served_ports() -> list[int]:
    """Which local ports are currently proxied."""
    try:
        data = json.loads(_run(["serve", "status", "--json"]) or "{}")
    except (TailscaleError, json.JSONDecodeError):
        return []
    ports: set[int] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "Proxy" and isinstance(value, str) and ":" in value:
                    tail = value.rsplit(":", 1)[1]
                    if tail.isdigit():
                        ports.add(int(tail))
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return sorted(ports)


def reset() -> None:
    """Take every serve mapping on this machine down, not only ours."""
    _run(["serve", "reset"], timeout=30)
