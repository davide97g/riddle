"""Look at the diary's hand before letting it near the page.

Skeletonised text has one failure mode the Hershey fonts never had: thinning
can break a letter that was rasterised too light or too small, and you cannot
tell from the numbers. So this writes the ink to a PNG at page scale, where a
broken stem is obvious, and only puts it on the tablet if asked.

    riddle write "text to write"             # preview to a png
    riddle write "text to write" --yes       # and draw it on the open page
"""

from pathlib import Path


from PIL import Image, ImageDraw

from riddle import config, consent, paths
from riddle.ink import hershey
from riddle.ink.geometry import SCREEN_H, SCREEN_W
from riddle.ink.style import Palette

MARGIN = 90
DEFAULT = "I remember every page you gave me, and I keep *all* of them"


def ink(text: str, height: float) -> list[hershey.Polyline]:
    cfg = config.get()
    palette = Palette(body=cfg.font_body, accent=cfg.font_accent)
    runs = palette.runs(text, height)
    max_width = SCREEN_W - 2 * MARGIN
    rows = hershey.line_count(runs, max_width)
    tallest = max(run.height for run in runs)
    return hershey.layout_runs(
        runs,
        center_x=SCREEN_W / 2,
        baseline=(SCREEN_H - (rows - 1) * tallest * 1.9) / 2,
        max_width=max_width,
    )


def preview(strokes: list[hershey.Polyline], out: Path) -> None:
    page = Image.new("L", (SCREEN_W, SCREEN_H), 255)
    pen = ImageDraw.Draw(page)
    for path in strokes:
        if len(path) > 1:
            pen.line([(x, y) for x, y in path], fill=0, width=3)
    out.parent.mkdir(parents=True, exist_ok=True)
    page.save(out)
    points = sum(len(path) for path in strokes)
    print(f"{len(strokes)} strokes, {points} points -> {out}")


def run(args) -> int:
    cfg = config.get()
    text = args.text or DEFAULT
    strokes = ink(text, float(args.height or cfg.ink_height))
    preview(strokes, args.out or (paths.VAR / "handwriting.png"))

    if not args.yes:
        return 0

    import time

    from riddle.device import Device

    consent.draw("write a line of handwriting", yes=args.yes)
    device = Device(host=args.host or cfg.ssh_host)
    time.sleep(1.5)
    device.select("pen")
    device.draw(strokes, pressure=cfg.pressure, step_ms=6)
    device.sync()
    device.close()
    print("written")
    return 0
