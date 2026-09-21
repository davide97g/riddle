"""Record the taps that select a tool, so they can be replayed later.

    riddle taps learn pen --yes

Tap the buttons on the tablet as you normally would, then press Enter here,
or pass --seconds N to record for a fixed stretch instead.

This needs --yes like anything else that touches the tablet: replaying what
it records presses buttons on the live toolbar, and a press in the wrong
place changes the tool or leaves a mark.
"""

import queue
import threading
import time
from pathlib import Path


from riddle import config, consent
from riddle.device import taps
from riddle.device import Device, PenUp, Sample, Touch

SETTLE = 0.35  # a tap is a burst of samples; this much silence ends one


def _centre(burst: list[tuple[str, float, float]]) -> dict:
    """Middle of a burst of samples: where the press actually landed."""
    kind = burst[0][0]
    xs = sorted(p[1] for p in burst)
    ys = sorted(p[2] for p in burst)
    return {"kind": kind, "x": round(xs[len(xs) // 2], 1), "y": round(ys[len(ys) // 2], 1)}


def run(args) -> int:
    consent.draw(f"record the taps that select {args.name!r}", yes=args.yes)
    device = Device(host=args.host or config.get().ssh_host)
    time.sleep(1.5)
    print(f"recording taps for {args.name!r}. tap the tablet, then press Enter here.")

    recorded: list[dict] = []
    burst: list[tuple[str, float, float]] = []
    last = 0.0

    done = threading.Event()
    if args.seconds:
        print(f"listening for {args.seconds:.0f}s")
        threading.Timer(args.seconds, done.set).start()
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
        print("no taps recorded")
        return 1
    taps.save(args.name, recorded)
    print(f"saved {len(recorded)} tap(s) as {args.name!r} in {taps.STORE}")
    return 0


def show(args) -> int:
    known = taps.load()
    if args.name:
        found = known.get(args.name)
        if not found:
            print(f"no taps recorded for {args.name!r}")
            return 1
        for tap in found:
            print(f"  {tap}")
        return 0
    if not known:
        print(f"nothing recorded yet in {taps.STORE}")
        return 1
    for name, recorded in known.items():
        print(f"{name}: {len(recorded)} tap(s)")
    return 0
