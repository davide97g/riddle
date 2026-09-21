#!/usr/bin/env python3
"""Draw a picture and a diagram, to see how the pen handles each."""

import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guard import consent

import draw
from device import Device
from diagram import Diagram, Node
from hershey import Font, Run, layout_runs

SANS = Font("futural")


def flowchart() -> list[draw.Polyline]:
    d = Diagram()
    d.add(Node("write", "you write", 90, 140, 320, 110, shape="round"))
    d.add(Node("pause", "pause 3s", 90, 380, 320, 110, shape="ellipse"))
    d.add(Node("read", "diary reads\nthe page", 90, 620, 320, 130))
    d.add(Node("erase", "ink vanishes", 560, 620, 320, 130, shape="round"))
    d.add(Node("reply", "diary answers\nin ink", 1000, 620, 330, 130, shape="round"))
    d.connect("write", "pause")
    d.connect("pause", "read")
    d.connect("read", "erase")
    d.connect("erase", "reply")
    return d.strokes()


def snake() -> list[draw.Polyline]:
    """A coiling snake: long smooth curves are what the pen does best."""
    body_top = []
    body_bottom = []
    for i in range(140):
        t = i / 139
        x = 180 + t * 1040
        wave = math.sin(t * math.pi * 2.4) * 150
        taper = 34 * (1 - t) + 4
        body_top.append((x, 1180 + wave - taper))
        body_bottom.append((x, 1180 + wave + taper))
    head = draw.ellipse(190, 1180 + math.sin(0) * 150, 58, 40)
    eye = draw.circle(205, 1168, 6, steps=12)
    tongue = [
        [(135, 1180), (95, 1180)],
        [(95, 1180), (70, 1168)],
        [(95, 1180), (70, 1192)],
    ]
    scales = []
    for i in range(6, 140, 10):
        t = i / 139
        x = 180 + t * 1040
        wave = math.sin(t * math.pi * 2.4) * 150
        taper = 34 * (1 - t) + 4
        scales.append(draw.arc(x, 1180 + wave, taper * 0.8, 200, 340, steps=8))
    return [body_top, body_bottom, head, eye, *tongue, *scales]


if __name__ == "__main__":
    consent("draw the demo scene")
    strokes = flowchart() + snake()
    strokes += layout_runs(
        [Run("nothing here is a font or a bitmap", SANS, 30)],
        center_x=702,
        baseline=1500,
        max_width=1200,
    )
    print(f"{len(strokes)} strokes, {sum(len(s) for s in strokes)} points")

    device = Device()
    time.sleep(1.5)
    start = time.monotonic()
    device.draw(strokes, pressure=3000, step_ms=1)
    device.sync()
    print(f"drawn in {time.monotonic() - start:.1f}s")
    device.close()
