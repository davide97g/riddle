#!/usr/bin/env python3
"""Put a diagram, a drawing and a traced photograph on one page.

Three different ways of getting ink onto the tablet, so the cost and the look
of each can be compared side by side.
"""

import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import draw
import image
import page
from device import Device, _resample
from diagram import Diagram, Node
from guard import consent
from hershey import Font, Run, layout_runs

SANS = Font("futural")
PHOTO = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None


def caption(text: str, x: float, y: float, height: float = 26):
    return layout_runs([Run(text, SANS, height)], center_x=x, baseline=y, max_width=700)


def flowchart() -> list[draw.Polyline]:
    d = Diagram()
    d.add(Node("write", "you write", 70, 150, 270, 96, shape="round"))
    d.add(Node("pause", "pause 3s", 70, 330, 270, 96, shape="ellipse"))
    d.add(Node("read", "diary reads", 70, 510, 270, 96))
    d.add(Node("erase", "ink vanishes", 70, 690, 270, 96, shape="round"))
    for a, b in (("write", "pause"), ("pause", "read"), ("read", "erase")):
        d.connect(a, b)
    return d.strokes() + caption("a diagram", 205, 120, 30)


def snake() -> list[draw.Polyline]:
    top, bottom, scales = [], [], []
    for i in range(120):
        t = i / 119
        x = 120 + t * 560
        wave = math.sin(t * math.pi * 2.2) * 70
        taper = 26 * (1 - t) + 3
        top.append((x, 1180 + wave - taper))
        bottom.append((x, 1180 + wave + taper))
        if i % 10 == 5:
            scales.append(draw.arc(x, 1180 + wave, taper * 0.8, 200, 340, steps=8))
    head = draw.ellipse(128, 1180, 44, 30)
    eye = draw.circle(140, 1170, 5, steps=10)
    tongue = [[(90, 1180), (58, 1180)], [(58, 1180), (36, 1170)], [(58, 1180), (36, 1190)]]
    return [top, bottom, head, eye, *tongue, *scales] + caption("a drawing", 400, 1100, 30)


def photo() -> list[draw.Polyline]:
    if PHOTO is None or not PHOTO.exists():
        return []
    traced = image.trace(PHOTO, levels=(60, 105, 150, 195), width=210)
    placed = image.place(traced, (740, 170, 560, 720))
    return placed + caption("a photograph, contour traced", 1020, 140, 28)


if __name__ == "__main__":
    strokes = flowchart() + snake() + photo()
    injected = sum(len(_resample(s, 3.0)) for s in strokes)
    print(f"{len(strokes)} strokes, {injected} injected points")
    print(f"rough estimate: {(injected * 3 + len(strokes) * 20) / 1000:.0f}s")

    consent("draw the gallery page")
    device = Device()
    time.sleep(1.5)
    start = time.monotonic()
    if "--clear" in sys.argv:
        # Same session as the drawing, so the page cannot change in between.
        device.draw(page.sweep(), eraser=True, step_ms=1, spacing=16.0, settle_ms=4)
    device.draw(strokes, pressure=3000, step_ms=1)
    device.sync()
    print(f"drawn in {time.monotonic() - start:.1f}s")
    device.close()
