"""Single-stroke text rendering with the Hershey vector fonts.

A normal font would give us filled outlines, which a pen can only trace as
hollow letters. The Hershey set is centreline vector data, so each glyph is
already the path a nib would take -- exactly what we hand back to the
digitizer as ink.

scripts is a light cursive and reads as handwriting; futural is a plain sans
and is the one to pick when legibility matters more than character.
"""

from dataclasses import dataclass
from pathlib import Path

from riddle.paths import FONT_DIR

# Hershey coordinates are offsets from the character 'R'; glyphs span roughly
# 32 units vertically, which is what we scale against.
_ORIGIN = ord("R")
_UNITS_PER_EM = 32.0

Polyline = list[tuple[float, float]]


class Font:
    def __init__(self, name: str = "scripts") -> None:
        self.name = name
        self.glyphs = _parse(FONT_DIR / f"{name}.jhf")

    def advance(self, ch: str, scale: float) -> float:
        left, right, _ = self.glyphs.get(ord(ch), self.glyphs[ord(" ")])
        return (right - left) * scale

    def width(self, text: str, scale: float) -> float:
        return sum(self.advance(ch, scale) for ch in text)

    def glyph(self, ch: str, pen_x: float, baseline: float, scale: float) -> list[Polyline]:
        glyph = self.glyphs.get(ord(ch))
        if glyph is None:
            return []
        left, _, paths = glyph
        return [
            [((x - left) * scale + pen_x, y * scale + baseline) for x, y in path]
            for path in paths
        ]


def _parse(path: Path) -> dict[int, tuple[int, int, list[Polyline]]]:
    glyphs: dict[int, tuple[int, int, list[Polyline]]] = {}
    # The .jhf file holds one glyph per line in ASCII order starting at space.
    for index, line in enumerate(path.read_text().splitlines()):
        if len(line) < 10:
            continue
        body = line[8:]
        left = ord(body[0]) - _ORIGIN
        right = ord(body[1]) - _ORIGIN
        paths: list[Polyline] = []
        current: Polyline = []
        for i in range(2, len(body) - 1, 2):
            pair = body[i : i + 2]
            if pair == " R":
                if current:
                    paths.append(current)
                current = []
                continue
            current.append((ord(pair[0]) - _ORIGIN, ord(pair[1]) - _ORIGIN))
        if current:
            paths.append(current)
        glyphs[32 + index] = (left, right, paths)
    return glyphs


@dataclass
class Run:
    """A span of the reply that shares one font, size and weight."""

    text: str
    font: "Font"
    height: float
    bold: bool = False

    @property
    def scale(self) -> float:
        return self.height / _UNITS_PER_EM


@dataclass
class _Word:
    text: str
    run: Run

    @property
    def width(self) -> float:
        return self.run.font.width(self.text, self.run.scale)


def _word_strokes(word: _Word, pen_x: float, baseline: float) -> list[Polyline]:
    """Ink for one word, asking the font for the whole word when it can.

    A joined hand has to be drawn a word at a time: in cursive the exit of one
    letter is the entry of the next, so setting glyphs side by side from their
    advance widths leaves a gap at every join. The Hershey fonts are unjoined
    and have no such method, so they are still stepped letter by letter.
    """
    run = word.run
    whole = getattr(run.font, "word", None)
    if whole is not None:
        return whole(word.text, pen_x, baseline, run.scale)

    strokes: list[Polyline] = []
    for ch in word.text:
        strokes.extend(run.font.glyph(ch, pen_x, baseline, run.scale))
        pen_x += run.font.advance(ch, run.scale)
    return strokes


def _embolden(strokes: list[Polyline], offset: float) -> list[Polyline]:
    """Fake a heavier nib by tracing each path again, just beside itself."""
    doubled = list(strokes)
    for path in strokes:
        doubled.append([(x + offset, y) for x, y in path])
        doubled.append([(x, y + offset) for x, y in path])
    return doubled


def layout_runs(
    runs: list[Run],
    center_x: float,
    baseline: float,
    max_width: float,
    line_gap: float = 1.9,
    bold_offset: float = 2.2,
) -> list[Polyline]:
    """Lay out styled runs as centred lines of single-stroke text."""
    words: list[_Word] = []
    for run in runs:
        for word in run.text.split():
            words.append(_Word(word, run))
    if not words:
        return []

    space = lambda run: run.font.advance(" ", run.scale)

    lines: list[list[_Word]] = [[]]
    width = 0.0
    for word in words:
        gap = space(word.run) if lines[-1] else 0.0
        if lines[-1] and width + gap + word.width > max_width:
            lines.append([word])
            width = word.width
        else:
            lines[-1].append(word)
            width += gap + word.width

    strokes: list[Polyline] = []
    pen_y = baseline
    for line in lines:
        line_height = max(word.run.height for word in line)
        total = sum(word.width for word in line) + sum(
            space(word.run) for word in line[1:]
        )
        pen_x = center_x - total / 2
        for index, word in enumerate(line):
            if index:
                pen_x += space(word.run)
            glyphs = _word_strokes(word, pen_x, pen_y)
            strokes.extend(
                _embolden(glyphs, bold_offset) if word.run.bold else glyphs
            )
            pen_x += word.width
        pen_y += line_height * line_gap
    return strokes


def line_count(runs: list[Run], max_width: float) -> int:
    """How many lines layout_runs will produce, for vertical centring."""
    words = [_Word(w, run) for run in runs for w in run.text.split()]
    if not words:
        return 0
    rows, width = 1, 0.0
    for index, word in enumerate(words):
        gap = word.run.font.advance(" ", word.run.scale) if index else 0.0
        if index and width + gap + word.width > max_width:
            rows += 1
            width = word.width
        else:
            width += gap + word.width
    return rows


def wrap(text: str, font: Font, scale: float, max_width: float) -> list[str]:
    lines: list[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if line and font.width(candidate, scale) > max_width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines
