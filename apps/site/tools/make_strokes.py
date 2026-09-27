"""Write the pen strokes the landing page draws, out of the diary itself.

Nothing on the page is a font. The replies are laid out by the same code
the loop uses to answer on the tablet (`riddle.tools.handwriting.ink`), so a
short answer comes out in the joined Dancing Script hand and a word in
*asterisks* is leaned on, exactly as it would be on paper. The questions are
in a Hershey script, a different hand, because they stand for yours. The
wordmark is apps/web/src/lib/wordmark.ts, the splash's own paths.

Coordinates are the tablet's page, 1404x1872, so the page on the site is the
page on the tablet.

    .venv/bin/python apps/site/tools/make_strokes.py
"""

import json
import re
from pathlib import Path

from riddle.ink import hershey
from riddle.ink.geometry import SCREEN_W
from riddle.ink.style import Palette
from riddle.tools.handwriting import ink

HERE = Path(__file__).resolve().parent
SITE = HERE.parent
ROOT = SITE.parents[1]
OUT = SITE / "assets" / "strokes.json"

# What a visitor sees the diary asked and answered. Short on purpose: ten
# words or fewer is the cursive hand, which is the one worth watching.
PAIRS = [
    ("who are you?", "Someone who keeps your pages."),
    ("will it rain tomorrow?", "Ask the window. I only know *paper*."),
    ("what should I write?", "Whatever you would not *say*."),
]
# For a page somebody scribbled on themselves: the demo cannot read it, so it
# answers the way the diary answers a drawing it does not understand.
SCRIBBLE = [
    "I cannot read that, but I *like* it.",
    "Write it again, slower.",
    "That looks like a *secret*.",
]

# Lines drawn on their own, cropped to their ink: the README's instruction,
# which is the whole manual, and something the diary kept about you.
# The skeletonised hand has no full stops, so the manifesto is three lines
# and the line breaks do the punctuating.
LINES = {
    "manifesto": ["Write something", "Stop", "Wait *three seconds*"],
    "memory": ["You told me about the *train*"],
}

QUESTION_HEIGHT = 165
ANSWER_HEIGHT = 185


def question(text: str, baseline: float) -> list:
    font = hershey.Font("scripts")
    runs = [hershey.Run(text, font, QUESTION_HEIGHT)]
    return hershey.layout_runs(runs, center_x=SCREEN_W / 2, baseline=baseline, max_width=SCREEN_W - 260)


def answer(text: str, baseline: float) -> list:
    lines = ink(text, ANSWER_HEIGHT)
    # `ink` centres on the page; move it to where the answer belongs, under
    # the question, the way the loop does.
    top = min(y for line in lines for _, y in line)
    return [[(x, y - top + baseline) for x, y in line] for line in lines]


def pack(lines) -> list:
    """Whole pixels and no single-point dabs: the page draws them as paths."""
    out = []
    for line in lines:
        pts = [(round(x, 1), round(y, 1)) for x, y in line]
        if len(pts) > 1:
            out.append(pts)
    return out


def cropped(rows: list[str]) -> dict:
    """Each row laid out alone, stacked and centred, cropped to the ink."""
    stacked, y = [], 0.0
    blocks = []
    for text in rows:
        lines = pack(ink(text, 100))
        xs = [x for line in lines for x, _ in line]
        ys = [y_ for line in lines for _, y_ in line]
        blocks.append((lines, min(xs), max(xs), min(ys), max(ys)))
    width = max(x1 - x0 for _, x0, x1, _, _ in blocks)
    for lines, x0, x1, y0, y1 in blocks:
        dx = (width - (x1 - x0)) / 2 - x0
        stacked += [[(x + dx, yy - y0 + y) for x, yy in line] for line in lines]
        y += (y1 - y0) + 70
    xs = [x for line in stacked for x, _ in line]
    ys = [yy for line in stacked for _, yy in line]
    x0, y0 = min(xs) - 12, min(ys) - 12
    return {
        "w": round(max(xs) - x0 + 12, 1),
        "h": round(max(ys) - y0 + 12, 1),
        "strokes": [[(round(x - x0, 1), round(yy - y0, 1)) for x, yy in line] for line in stacked],
    }


def wordmark() -> dict:
    text = (ROOT / "apps" / "web" / "src" / "lib" / "wordmark.ts").read_text()
    return {
        "width": float(re.search(r"width: ([\d.]+)", text).group(1)),
        "height": float(re.search(r"height: ([\d.]+)", text).group(1)),
        "nib": float(re.search(r"nib: ([\d.]+)", text).group(1)),
        "strokes": re.findall(r"d: '([^']+)'", text),
    }


def main() -> None:
    data = {
        "page": [1404, 1872],
        "pairs": [
            {"q": q, "a": a, "question": pack(question(q, 520)), "answer": pack(answer(a, 860))}
            for q, a in PAIRS
        ],
        "scribble": [{"a": a, "answer": pack(answer(a, 1180))} for a in SCRIBBLE],
        "lines": {name: cropped(rows) for name, rows in LINES.items()},
        "wordmark": wordmark(),
    }
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
