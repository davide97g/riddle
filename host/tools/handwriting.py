#!/usr/bin/env python3
"""Look at the diary's hand before letting it near the page.

Skeletonised text has one failure mode the Hershey fonts never had: thinning
can break a letter that was rasterised too light or too small, and you cannot
tell from the numbers. So this writes the ink to a PNG at page scale, where a
broken stem is obvious, and only puts it on the tablet if asked.

    handwriting.py "text to write"           # preview to /tmp/handwriting.png
    handwriting.py "text to write" --yes     # and draw it on the open page
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw

import hershey
from geometry import SCREEN_H, SCREEN_W
from style import Palette

OUT = Path("/tmp/handwriting.png")
MARGIN = 90
DEFAULT = "I remember every page you gave me, and I keep *all* of them"


def ink(text: str, height: float) -> list[hershey.Polyline]:
    palette = Palette(
        body=os.environ.get("RIDDLE_FONT_BODY", "futural"),
        accent=os.environ.get("RIDDLE_FONT_ACCENT", "DancingScript"),
    )
    runs = palette.runs(text, height)
    max_width = SCREEN_W - 2 * MARGIN
    rows = hershey.line_count(runs, max_width)
    tallest = max(run.height for run in runs)
    return hershey.layout_runs(
        runs,
        center_x=SCREEN_W / 2,
        baseline=(SCREEN_H - (rows - 1) * tallest * 1.9) / 2,
        max_width=max_width,
    )


def preview(strokes: list[hershey.Polyline]) -> None:
    page = Image.new("L", (SCREEN_W, SCREEN_H), 255)
    pen = ImageDraw.Draw(page)
    for path in strokes:
        if len(path) > 1:
            pen.line([(x, y) for x, y in path], fill=0, width=3)
    page.save(OUT)
    points = sum(len(path) for path in strokes)
    print(f"{len(strokes)} strokes, {points} points -> {OUT}")


def main() -> None:
    words = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    text = " ".join(words) or DEFAULT
    height = float(os.environ.get("RIDDLE_INK_HEIGHT", "72"))

    strokes = ink(text, height)
    preview(strokes)

    if "--yes" not in sys.argv:
        return

    import time

    from device import Device
    from guard import consent

    consent("write a line of handwriting")
    device = Device(host=os.environ.get("RM2_SSH_HOST", "rm2"))
    time.sleep(1.5)
    device.select("pen")
    device.draw(
        strokes,
        pressure=int(os.environ.get("RIDDLE_PRESSURE", "3200")),
        step_ms=6,
    )
    device.sync()
    device.close()
    print("written")


if __name__ == "__main__":
    main()
