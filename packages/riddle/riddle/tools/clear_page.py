#!/usr/bin/env python3
"""Wipe the visible page with the eraser."""

import sys
import time
from pathlib import Path


from riddle.ink import page
from riddle.device import Device
from riddle.consent import consent

if __name__ == "__main__":
    consent("erase the whole page")
    device = Device()
    time.sleep(1.5)
    passes = page.sweep()
    print(f"erasing in {len(passes)} passes")
    device.draw(passes, eraser=True, step_ms=1, spacing=16.0, settle_ms=4)
    device.sync()
    device.close()
    print("page cleared")
