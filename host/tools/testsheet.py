#!/usr/bin/env python3
"""Draw a sheet that shows where injected ink stops being usable.

Fine gaps, small type and tight hatching all collapse at some point, partly
because xochitl smooths what it thinks is a hand stroke and partly because
e-ink cannot hold the detail. This sheet puts those ladders side by side so
the floor can be read off the page.
"""

import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guard import consent

import draw
from device import Device
from hershey import Font, Run, layout_runs

SANS = Font("futural")
SCRIPT = Font("scripts")


def label(text: str, x: float, y: float, height: float = 24, font: Font = SANS):
    return layout_runs([Run(text, font, height)], center_x=x, baseline=y, max_width=600)


def sheet() -> list[draw.Polyline]:
    out: list[draw.Polyline] = []

    out += label("INJECTION LIMITS", 702, 90, 44)

    # Gap ladder: pairs of lines at shrinking separation.
    out += label("line gap px", 160, 170, 24)
    x = 300.0
    for gap in (24, 18, 14, 10, 8, 6, 4, 3, 2):
        out.append(draw.line((x, 140), (x, 230)))
        out.append(draw.line((x + gap, 140), (x + gap, 230)))
        out += label(str(gap), x + gap / 2, 262, 22)
        x += gap + 74

    # Type ladder in both hands.
    y = 330.0
    for height in (56, 44, 34, 26, 20, 16):
        out += label(f"diary {height}", 360, y, height, SANS)
        out += label(f"diary {height}", 1000, y, height, SCRIPT)
        y += height * 1.9

    # Hatch density.
    out += label("hatch spacing", 200, 780, 24)
    x = 120.0
    for spacing in (20, 14, 10, 7, 5):
        out.append(draw.rect(x, 800, 200, 130))
        out += draw.hatch(x + 4, 804, 192, 122, spacing=spacing)
        out += label(str(spacing), x + 100, 962, 22)
        x += 250

    # Small closed shapes.
    out += label("circle radius", 200, 1030, 24)
    x = 160.0
    for r in (60, 40, 25, 15, 8, 4):
        out.append(draw.circle(x, 1120, r, steps=max(12, int(r))))
        out += label(str(r), x, 1215, 22)
        x += 170

    # Curves and a function plot.
    out.append(draw.plot(lambda t: math.sin(t) * math.exp(-t / 6), 0, 18, (140, 1280, 1120, 220)))
    out.append(draw.line((140, 1390), (1260, 1390)))
    out += label("damped sine", 702, 1540, 28)

    # Corner registration marks, to check the mapping has no drift.
    for cx, cy in ((40, 40), (1364, 40), (40, 1832), (1364, 1832)):
        out.append(draw.line((cx - 25, cy), (cx + 25, cy)))
        out.append(draw.line((cx, cy - 25), (cx, cy + 25)))

    # Dense detail: a spiral, to see where adjacent turns merge.
    spiral = []
    for i in range(720):
        angle = math.radians(i * 2)
        radius = 12 + i * 0.22
        spiral.append((702 + radius * math.cos(angle), 1690 + radius * math.sin(angle) * 0.6))
    out.append(spiral)

    return out


if __name__ == "__main__":
    consent("draw the test sheet")
    strokes = sheet()
    points = sum(len(s) for s in strokes)
    print(f"{len(strokes)} strokes, {points} raw points")

    device = Device()
    time.sleep(1.5)
    start = time.monotonic()
    device.draw(strokes, pressure=3000, step_ms=2)
    device.sync()
    elapsed = time.monotonic() - start
    print(f"drawn in {elapsed:.1f}s")
    device.close()
