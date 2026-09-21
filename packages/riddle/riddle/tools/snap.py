#!/usr/bin/env python3
"""Photograph the tablet's screen.

    host/tools/snap.py --yes [--scale 0.5] [-o captures/screen-<ts>.png]
"""

import argparse
import os
import sys
import time
from pathlib import Path


from riddle import paths
from riddle.device import screen



def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes", action="store_true", help="read the tablet's memory")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("-o", "--out", type=Path)
    args = ap.parse_args()

    screen.consent()
    out = args.out or paths.CAPTURES / f"screen-{int(time.time())}.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    began = time.monotonic()
    out.write_bytes(
        screen.png(host=os.environ.get("RM2_SSH_HOST", "rm2"), scale=args.scale)
    )
    where = paths.relative(out)
    print(f"{where} ({out.stat().st_size // 1024}K) in {time.monotonic() - began:.1f}s")


if __name__ == "__main__":
    main()
