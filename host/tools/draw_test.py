#!/usr/bin/env python3
"""Inject a known phrase so stroke injection can be eyeballed on the tablet."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guard import consent

import hershey
from device import Device

consent("inject test handwriting")
text = " ".join(sys.argv[1:]) or "i can hear you"
device = Device()
time.sleep(1.5)
strokes = hershey.layout(text, origin=(120, 600), height=60, max_x=1340)
print(f"injecting {len(strokes)} strokes")
device.draw(strokes, step_ms=3)
time.sleep(2)
device.close()
