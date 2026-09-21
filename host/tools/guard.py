"""Refuse to draw unless someone has just said it is safe to.

Injected strokes land in whatever notebook happens to be open, so every tool
that puts ink on the page asks first.
"""

import os
import sys

NOTEBOOK = os.environ.get("RIDDLE_NOTEBOOK", "Notebook 7")


def consent(action: str) -> None:
    if "--yes" in sys.argv or os.environ.get("RIDDLE_ALLOW_DRAW") == "1":
        print(f"{action} -> whatever notebook is open (expecting {NOTEBOOK!r})")
        return
    sys.exit(
        f"refusing to {action}: open {NOTEBOOK!r} on the tablet, then rerun with --yes"
    )
