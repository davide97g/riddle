"""Remembered taps for xochitl's toolbar.

Which pen is selected, and which mode the eraser is in, are UI state that the
digitizer cannot see or change: an injected stroke simply becomes whatever
tool is active, which is how a page of drawing turns into a page of lasso
selections. Rather than guess where the buttons are, we record it being done
once, by hand, and replay that.

A tap is stored with the device it came from, because the toolbar is usually
pressed with the pen rather than a finger, and the two speak different
coordinate systems.
"""

import json
from pathlib import Path

from riddle.paths import TAPS as STORE

Tap = dict[str, float | str]


def load() -> dict[str, list[Tap]]:
    if not STORE.exists():
        return {}
    return json.loads(STORE.read_text())


def save(name: str, taps: list[Tap]) -> None:
    current = load()
    current[name] = taps
    STORE.write_text(json.dumps(current, indent=2))


def get(name: str) -> list[Tap]:
    return load().get(name, [])
