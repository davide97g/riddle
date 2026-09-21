#!/usr/bin/env python3
"""Photograph the tablet's screen.

    host/tools/snap.py --yes [--scale 0.5] [-o captures/screen-<ts>.png]
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import snap

ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--yes", action="store_true", help="read the tablet's memory")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("-o", "--out", type=Path)
    args = ap.parse_args()

    snap.consent()
    out = args.out or ROOT / "captures" / f"screen-{int(time.time())}.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    began = time.monotonic()
    out.write_bytes(
        snap.png(host=os.environ.get("RM2_SSH_HOST", "rm2"), scale=args.scale)
    )
    where = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"{where} ({out.stat().st_size // 1024}K) in {time.monotonic() - began:.1f}s")


if __name__ == "__main__":
    main()
