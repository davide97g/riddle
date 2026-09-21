"""Decide how a reply should look on the page.

The diary does not write everything the same way. A long, plain answer wants
the legible sans hand so it can be read at a glance; a short retort, and any
word the diary leans on, gets the cursive hand, doubled up so it reads as
heavier ink.
"""

import re

from riddle.ink import hershey
from riddle.ink import skeleton
from riddle.ink.hershey import Run

EMPHASIS = re.compile(r"\*([^*]+)\*")

LONG_ANSWER_WORDS = 10

# Dancing Script is a joined hand and needs weight to survive thinning: at its
# lightest the skeleton comes out broken. This is the axis value, not a scale.
SKELETON_WEIGHT = 600


def load(name: str):
    """Open a font by name, whichever kind it turns out to be.

    A name matching a .ttf is skeletonised into pen paths; anything else is
    looked up in the Hershey set. Both answer the same calls, so the rest of
    the pipeline never has to ask which it is holding.
    """
    if (skeleton.FONT_DIR / f"{name}.ttf").exists():
        return skeleton.Font(name, weight=SKELETON_WEIGHT)
    return hershey.Font(name)


class Palette:
    def __init__(
        self, body: str = "futural", accent: str = "DancingScript"
    ) -> None:
        self.body = load(body)
        self.accent = load(accent)

    def runs(self, reply: str, height: float) -> list[Run]:
        plain = EMPHASIS.sub(r"\1", reply)
        long_answer = len(plain.split()) > LONG_ANSWER_WORDS

        body_font = self.body if long_answer else self.accent
        body_height = height * (0.78 if long_answer else 1.0)

        runs: list[Run] = []
        position = 0
        for match in EMPHASIS.finditer(reply):
            before = reply[position : match.start()]
            if before.strip():
                runs.append(Run(before, body_font, body_height))
            runs.append(
                Run(match.group(1), self.accent, body_height * 1.18, bold=True)
            )
            position = match.end()
        tail = reply[position:]
        if tail.strip():
            runs.append(Run(tail, body_font, body_height))
        return runs
