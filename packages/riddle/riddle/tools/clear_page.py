"""Wipe the visible page with the eraser."""

import time

from riddle import config, consent
from riddle.device import Device
from riddle.ink import page


def run(args) -> int:
    consent.draw("erase the whole page", yes=args.yes)
    device = Device(host=args.host or config.get().ssh_host)
    time.sleep(1.5)
    passes = page.sweep()
    print(f"erasing in {len(passes)} passes")
    device.draw(passes, eraser=True, step_ms=1, spacing=16.0, settle_ms=4)
    device.sync()
    device.close()
    print("page cleared")
    return 0
