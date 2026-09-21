"""Photograph the tablet's screen."""

import time

from riddle import config, consent, paths
from riddle.device import screen


def run(args) -> int:
    consent.screen("read the screen", yes=args.yes)
    out = args.out or paths.CAPTURES / f"screen-{int(time.time())}.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    began = time.monotonic()
    out.write_bytes(
        screen.png(host=args.host or config.get().ssh_host, scale=args.scale)
    )
    size = out.stat().st_size // 1024
    print(f"{paths.relative(out)} ({size}K) in {time.monotonic() - began:.1f}s")
    return 0
