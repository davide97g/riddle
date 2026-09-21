"""Draw a line-art image on the tablet.

Usage: picture.py <image> [--clear] [--yes] [--width N]
"""

import time
from pathlib import Path


from riddle.ink import lineart
from riddle.ink import page
from riddle.device import Device
from riddle.ink.geometry import resample
from riddle import config, consent

BOX = (90, 120, 1220, 1620)


def run(args) -> int:
    cfg = config.get()
    traced = lineart.render(
        args.image,
        width=args.width,
        fill_depth=4,
        hatch_spacing=3,
        min_length=2.0,
        epsilon=0.35,
    )
    strokes = lineart.place(traced, BOX)
    injected = sum(len(resample(s, 3.0)) for s in strokes)
    print(f"{len(strokes)} strokes, {injected} injected points")

    consent.draw(f"draw {args.image.name}", yes=args.yes)
    device = Device(host=args.host or cfg.ssh_host)
    time.sleep(1.5)
    start = time.monotonic()
    if args.clear:
        device.draw(page.sweep(), eraser=True, step_ms=1, spacing=16.0, settle_ms=4)
    # Erasing leaves xochitl on whatever tool it likes, so the pen is chosen
    # again as the last thing before any ink is laid down.
    device.select("pen")
    device.draw(strokes, pressure=cfg.pressure, step_ms=1)
    device.sync()
    print(f"drawn in {time.monotonic() - start:.1f}s")
    device.close()
    return 0
