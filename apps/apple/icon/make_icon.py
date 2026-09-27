"""Draw the app icon: "riddle" in the diary's own hand, bent round a circle.

The strokes are the wordmark's, read out of apps/web/src/lib/wordmark.ts --
the pen paths `riddle write "riddle"` lays down, the same ones the splash
draws -- so the icon is the machine's handwriting and not a font. Each
point is carried onto an arc: along the word becomes round the circle,
up the letter becomes out from its centre, and the middle of the x-height
keeps its length, so the letters fan a little above it and gather a
little below rather than all stretching one way.

The layer goes into Riddle/AppIcon.icon, the Icon Composer document Xcode
builds for both platforms; the glass, the shadow and the dark and tinted
renditions are the system's.

    .venv/bin/python apps/apple/icon/make_icon.py

Then look at it, the way the system will draw it:

    ictool apps/apple/Riddle/AppIcon.icon --export-image --output-file icon.png \
      --platform iOS --rendition Default --width 1024 --height 1024 --scale 1
"""

import math
import re
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "web" / "src" / "lib" / "wordmark.ts"
OUT = HERE.parent / "Riddle" / "AppIcon.icon" / "Assets"

SIZE = 1024
SS = 4  # supersampled, then reduced: the only antialiasing there is
INK = (24, 23, 30)

SCALE = 2.3  # icon pixels per wordmark unit; the cap height is 100 units
SPAN = math.radians(80)  # how far round the circle the word reaches
NIB = 1.45  # times the wordmark's own nib, which is drawn for a header


def wordmark():
    text = SOURCE.read_text()
    width = float(re.search(r"width: ([\d.]+)", text).group(1))
    height = float(re.search(r"height: ([\d.]+)", text).group(1))
    nib = float(re.search(r"nib: ([\d.]+)", text).group(1))
    paths = re.findall(r"d: '([^']+)'", text)
    return width, height, nib, paths


def polyline(d, per_curve=48):
    """Absolute M, L and C, which is all the generator writes."""
    tokens = re.findall(r"[MLC]|-?\d*\.?\d+", d)
    points, i, cmd, pen = [], 0, "M", (0.0, 0.0)
    while i < len(tokens):
        if tokens[i] in "MLC":
            cmd = tokens[i]
            i += 1
            continue
        if cmd in "ML":
            pen = (float(tokens[i]), float(tokens[i + 1]))
            points.append(pen)
            i += 2
        else:
            c1 = (float(tokens[i]), float(tokens[i + 1]))
            c2 = (float(tokens[i + 2]), float(tokens[i + 3]))
            end = (float(tokens[i + 4]), float(tokens[i + 5]))
            for k in range(1, per_curve + 1):
                t = k / per_curve
                u = 1 - t
                points.append((
                    u**3 * pen[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * end[0],
                    u**3 * pen[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * end[1],
                ))
            pen = end
            i += 6
    return points


def bend(width, height):
    """The map from the word's flat box onto the arc, in icon pixels."""
    middle = width * SCALE / SPAN  # radius where arc length is kept
    base = middle - height * SCALE / 2
    top = base + height * SCALE
    # Centred on the arc's own extent, top of the letters to the ends of
    # the baseline, so the word sits in the middle of the icon.
    low = base * math.cos(SPAN / 2)
    cy = SIZE / 2 + (top + low) / 2
    cx = SIZE / 2

    def place(x, y):
        theta = (x - width / 2) * SCALE / middle
        r = base + (height - y) * SCALE
        return cx + r * math.sin(theta), cy - r * math.cos(theta)

    return place


def layer():
    width, height, nib, paths = wordmark()
    place = bend(width, height)
    radius = nib * NIB * SCALE * SS / 2

    mask = Image.new("L", (SIZE * SS, SIZE * SS), 0)
    draw = ImageDraw.Draw(mask)
    for d in paths:
        pts = [place(x, y) for x, y in polyline(d)]
        # Dab a round nib along the curve, closer together than its own
        # radius so the stroke never beads.
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] or pts):
            steps = max(1, int(math.hypot(x1 - x0, y1 - y0) * SS / (radius / 3)))
            for k in range(steps + 1):
                x = (x0 + (x1 - x0) * k / steps) * SS
                y = (y0 + (y1 - y0) * k / steps) * SS
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=255)

    out = Image.new("RGBA", (SIZE, SIZE), INK + (0,))
    out.putalpha(mask.resize((SIZE, SIZE), Image.LANCZOS))
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    layer().save(OUT / "riddle.png")
    print(f"wrote {OUT / 'riddle.png'}")
