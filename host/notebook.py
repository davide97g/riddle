"""Identify the notebook the diary is meant to live in.

xochitl keeps the open document in memory and only writes it out when you
navigate away, and its config leaves LastOpen empty, so there is no live
reading of which notebook is on screen. The best we can do is resolve the
target by name, say so out loud at startup, and never draw unprompted.
"""

import subprocess

DATA_DIR = "/home/root/.local/share/remarkable/xochitl"

_REMOTE_LIST = (
    f"cd {DATA_DIR} && for f in *.metadata; do "
    "echo \"${f%.metadata} $(sed -n 's/.*\"visibleName\": *\"\\(.*\\)\".*/\\1/p' $f)\"; done"
)


def find(name: str, host: str = "rm2") -> str | None:
    """Return the uuid of the document with this exact visible name."""
    done = subprocess.run(
        ["ssh", host, _REMOTE_LIST], capture_output=True, text=True, timeout=60
    )
    for row in done.stdout.splitlines():
        uuid, _, title = row.partition(" ")
        if title.strip() == name:
            return uuid
    return None
