#!/usr/bin/env python3
"""Draw a line-art image on the tablet.

Usage: picture.py <image> [--clear] [--yes] [--width N]
"""

import sys
import time
from pathlib import Path


from riddle.ink import lineart
from riddle.ink import page
from riddle.device import Device
from riddle.ink.geometry import resample
from riddle.consent import consent

BOX = (90, 120, 1220, 1620)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit("usage: picture.py <image> [--clear] [--yes] [--width N]")
    source = Path(args[0])

    width = 760
    if "--width" in sys.argv:
        width = int(sys.argv[sys.argv.index("--width") + 1])

    traced = lineart.render(
        source,
        width=width,
        fill_depth=4,
        hatch_spacing=3,
        min_length=2.0,
        epsilon=0.35,
    )
    strokes = lineart.place(traced, BOX)
    injected = sum(len(resample(s, 3.0)) for s in strokes)
    print(f"{len(strokes)} strokes, {injected} injected points")

    consent(f"draw {source.name}")
    device = Device()
    time.sleep(1.5)
    start = time.monotonic()
    if "--clear" in sys.argv:
        device.draw(page.sweep(), eraser=True, step_ms=1, spacing=16.0, settle_ms=4)
    # Erasing leaves xochitl on whatever tool it likes, so the pen is chosen
    # again as the last thing before any ink is laid down.
    device.select("pen")
    device.draw(strokes, pressure=3200, step_ms=1)
    device.sync()
    print(f"drawn in {time.monotonic() - start:.1f}s")
    device.close()


if __name__ == "__main__":
    main()
