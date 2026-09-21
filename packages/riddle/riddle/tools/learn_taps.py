#!/usr/bin/env python3
"""Record the taps that select a tool, so they can be replayed later.

Usage: learn_taps.py <name>     e.g. learn_taps.py pen

Tap the buttons on the tablet as you normally would, then press Enter here,
or pass --seconds N to record for a fixed stretch instead.
"""

import queue
import sys
import time
from pathlib import Path


from riddle.device import taps
from riddle.device import Device, PenUp, Sample, Touch

SETTLE = 0.35  # a tap is a burst of samples; this much silence ends one


def _centre(burst: list[tuple[str, float, float]]) -> dict:
    """Middle of a burst of samples: where the press actually landed."""
    kind = burst[0][0]
    xs = sorted(p[1] for p in burst)
    ys = sorted(p[2] for p in burst)
    return {"kind": kind, "x": round(xs[len(xs) // 2], 1), "y": round(ys[len(ys) // 2], 1)}


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: learn_taps.py <name>")
    name = sys.argv[1]

    device = Device()
    time.sleep(1.5)
    print(f"recording taps for {name!r}. tap the tablet, then press Enter here.")

    recorded: list[dict] = []
    burst: list[tuple[str, float, float]] = []
    last = 0.0

    import threading

    done = threading.Event()
    if "--seconds" in sys.argv:
        window = float(sys.argv[sys.argv.index("--seconds") + 1])
        print(f"listening for {window:.0f}s")
        threading.Timer(window, done.set).start()
    else:
        threading.Thread(target=lambda: (input(), done.set()), daemon=True).start()

    while not done.is_set():
        try:
            event = device.events.get(timeout=0.1)
        except queue.Empty:
            event = None
        if isinstance(event, Touch):
            burst.append(("touch", event.x, event.y))
            last = time.monotonic()
        elif isinstance(event, Sample):
            # The toolbar is normally pressed with the pen, which arrives on
            # the digitizer in screen coordinates rather than as a finger.
            burst.append(("pen", event.x, event.y))
            last = time.monotonic()
        elif burst and time.monotonic() - last > SETTLE:
            recorded.append(_centre(burst))
            print(f"  tap {len(recorded)}: {recorded[-1]}")
            burst = []

    if burst:
        recorded.append(_centre(burst))
        print(f"  tap {len(recorded)}: {recorded[-1]}")

    device.close()
    if not recorded:
        sys.exit("no taps recorded")
    taps.save(name, recorded)
    print(f"saved {len(recorded)} tap(s) as {name!r} in {taps.STORE}")


if __name__ == "__main__":
    main()
