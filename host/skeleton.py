"""Turn an ordinary outline font into single-stroke pen paths.

The Hershey fonts exist because a pen cannot fill: given a normal TTF it would
trace the *outline* of each letter and you would get hollow, double-walled
text. Skeletonisation gets around that. Rasterise the word, thin the black
pixels down to a one-pixel ridge running along the middle of every stem, and
that ridge is the line a nib would have taken. Any font becomes a pen font.

The thinning is Zhang-Suen: repeatedly delete boundary pixels that are not
needed to keep the shape connected, until nothing more can go. It is written
here against whole neighbourhood arrays rather than pixel by pixel, because in
plain Python the per-pixel form takes seconds per word.

Words are rasterised whole, not letter by letter. In a joined hand like Dancing
Script the exit stroke of one letter *is* the entry stroke of the next, so
cutting glyphs apart and relying on advance widths to line them back up leaves
visible breaks at every join.
"""

from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).parent / "fonts"

# Hershey glyphs span about 32 units vertically and the rest of the pipeline is
# written against that, so we report metrics in the same em box. Nothing above
# this module needs to know which kind of font it is holding.
UNITS_PER_EM = 32.0

# Rasterise this much taller than the em box. Too small and the skeleton comes
# out lumpy; too large and thinning gets slow for no visible gain on a screen
# that smooths our strokes anyway.
RASTER_PX = 96

# The skeleton is a chain of single pixels, which is far more detail than the
# digitizer can use. Drop points that sit within this many raster pixels of the
# straight line they are already on.
SIMPLIFY_PX = 0.8

# Skeletons of round letters throw off short whiskers at stroke ends. Anything
# shorter than this many raster pixels is noise, not ink.
MIN_BRANCH_PX = 3.0

Polyline = list[tuple[float, float]]

# Eight neighbours in clockwise order starting north, which is the order
# Zhang-Suen's transition count is defined against.
_NEIGHBOURS = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]


def _shift(image: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """The image moved by (dy, dx), padding the exposed edge with zeros."""
    out = np.zeros_like(image)
    ys = slice(max(0, dy), image.shape[0] + min(0, dy))
    xs = slice(max(0, dx), image.shape[1] + min(0, dx))
    yt = slice(max(0, -dy), image.shape[0] + min(0, -dy))
    xt = slice(max(0, -dx), image.shape[1] + min(0, -dx))
    out[yt, xt] = image[ys, xs]
    return out


def thin(image: np.ndarray) -> np.ndarray:
    """Zhang-Suen thinning: a boolean mask reduced to one-pixel-wide ridges."""
    current = image.astype(bool)
    while True:
        removed = False
        for step in (0, 1):
            neighbours = [_shift(current, dy, dx) for dy, dx in _NEIGHBOURS]
            # B: how many of the eight neighbours are set.
            filled = sum(n.astype(np.uint8) for n in neighbours)
            # A: how many times the ring flips off->on as you walk it once.
            ring = neighbours + [neighbours[0]]
            transitions = sum(
                (~ring[i] & ring[i + 1]).astype(np.uint8) for i in range(8)
            )
            north, east, south, west = (
                neighbours[0],
                neighbours[2],
                neighbours[4],
                neighbours[6],
            )
            # Both corner tests must hold, not either: they are what stops a
            # diagonal stem being eaten from both sides at once.
            if step == 0:
                corners = (~(north & east & south)) & (~(east & south & west))
            else:
                corners = (~(north & east & west)) & (~(north & south & west))

            doomed = current & (filled >= 2) & (filled <= 6) & (transitions == 1) & corners
            if doomed.any():
                current = current & ~doomed
                removed = True
        if not removed:
            return current


def _edges(points: set[tuple[int, int]]) -> dict:
    """Adjacency for the skeleton, with redundant diagonals dropped.

    After thinning a stem is one pixel wide, but an 8-connected staircase still
    reports a diagonal link alongside the two orthogonal ones that already join
    the same pair. Left in, those shortcuts fork the walk and shed the stray
    two-point fragments that make a word look shredded.
    """
    links: dict[tuple[int, int], set[tuple[int, int]]] = {p: set() for p in points}
    for y, x in points:
        for dy, dx in _NEIGHBOURS:
            other = (y + dy, x + dx)
            if other not in points:
                continue
            if dy and dx:  # diagonal: skip if an orthogonal detour exists
                if (y + dy, x) in points or (y, x + dx) in points:
                    continue
            links[(y, x)].add(other)
            links[other].add((y, x))
    return links


def _walk(
    node: tuple[int, int],
    step: tuple[int, int],
    links: dict,
    used: set,
) -> list[tuple[int, int]]:
    """Follow a chain of degree-2 pixels until it hits a junction or an end."""
    path = [node, step]
    used.add(frozenset((node, step)))
    while len(links[path[-1]]) == 2:
        here = path[-1]
        nxt = next(p for p in links[here] if p != path[-2])
        edge = frozenset((here, nxt))
        if edge in used:
            break
        used.add(edge)
        path.append(nxt)
        if nxt == path[0]:  # closed loop, back where we started
            break
    return path


def _trace(mask: np.ndarray) -> list[Polyline]:
    """Walk a thinned mask into ordered polylines along its own anatomy.

    The skeleton is treated as a graph. Every run of degree-2 pixels between
    two junctions (or ends) becomes one polyline, so a stroke is drawn the way
    it was written rather than in whatever order the pixels were scanned.
    Anything left over is a closed loop, like the bowl of an 'o', and may start
    anywhere on itself.
    """
    points = {(int(y), int(x)) for y, x in zip(*np.nonzero(mask))}
    if not points:
        return []
    links = _edges(points)
    used: set = set()
    paths: list[list[tuple[int, int]]] = []

    # Open runs first, starting from ends and junctions.
    for node in sorted(points):
        if len(links[node]) == 2:
            continue
        for step in sorted(links[node]):
            if frozenset((node, step)) in used:
                continue
            paths.append(_walk(node, step, links, used))

    # Whatever survives is a cycle that never touched a junction.
    for node in sorted(points):
        for step in sorted(links[node]):
            if frozenset((node, step)) not in used:
                paths.append(_walk(node, step, links, used))

    return [[(float(x), float(y)) for y, x in path] for path in paths if len(path) > 1]


def _prune(paths: list[Polyline], min_length: float) -> list[Polyline]:
    """Drop the short whiskers thinning grows at stroke ends.

    A spur is short *and* hangs off something: one of its tips is shared with
    another path. That last test is what keeps the dot on an 'i', which is also
    short but stands alone.
    """
    tips: dict[tuple[float, float], int] = {}
    for path in paths:
        for tip in (path[0], path[-1]):
            tips[tip] = tips.get(tip, 0) + 1
    kept = []
    for path in paths:
        attached = tips[path[0]] > 1 or tips[path[-1]] > 1
        if attached and _length(path) < min_length:
            continue
        kept.append(path)
    return kept


def _stitch(paths: list[Polyline]) -> list[Polyline]:
    """Join paths that share a tip, so the pen lifts as rarely as it can.

    Every separate path costs a pen-down and a pen-up on the tablet, and each
    of those is a place xochitl can leave a blot, so it is worth chaining runs
    that simply continue one another.
    """
    pool = [list(p) for p in paths]
    out: list[Polyline] = []
    while pool:
        run = pool.pop()
        joined = True
        while joined:
            joined = False
            for i, other in enumerate(pool):
                if other[0] == run[-1]:
                    run += other[1:]
                elif other[-1] == run[-1]:
                    run += other[::-1][1:]
                elif other[-1] == run[0]:
                    run = other[:-1] + run
                elif other[0] == run[0]:
                    run = other[::-1][:-1] + run
                else:
                    continue
                pool.pop(i)
                joined = True
                break
        out.append(run)
    return out


def _turn_cost(path: list[tuple[int, int]], candidate: tuple[int, int]) -> float:
    if len(path) < 2:
        return 0.0
    (py, px), (cy, cx) = path[-2], path[-1]
    heading = math.atan2(cy - py, cx - px)
    step = math.atan2(candidate[0] - cy, candidate[1] - cx)
    return abs(math.atan2(math.sin(step - heading), math.cos(step - heading)))


def _length(path: Polyline) -> float:
    return sum(
        math.dist(path[i], path[i + 1]) for i in range(len(path) - 1)
    )


def _simplify(path: Polyline, tolerance: float) -> Polyline:
    """Ramer-Douglas-Peucker, so a straight stem is two points and not fifty.

    Kept iterative: a skeleton run can be hundreds of pixels long and the
    recursive form bottoms out against Python's stack on the worst of them.
    """
    if len(path) < 3:
        return path
    keep = [False] * len(path)
    keep[0] = keep[-1] = True
    pending = [(0, len(path) - 1)]
    while pending:
        first, last = pending.pop()
        if last <= first + 1:
            continue
        start, end = path[first], path[last]
        span = math.dist(start, end)
        worst, index = -1.0, first
        for i in range(first + 1, last):
            point = path[i]
            if span == 0:
                offset = math.dist(point, start)
            else:
                offset = abs(
                    (end[0] - start[0]) * (start[1] - point[1])
                    - (start[0] - point[0]) * (end[1] - start[1])
                ) / span
            if offset > worst:
                worst, index = offset, i
        if worst > tolerance:
            keep[index] = True
            pending.append((first, index))
            pending.append((index, last))
    return [point for point, kept in zip(path, keep) if kept]


class Font:
    """A TTF presented as pen paths, with the same surface as hershey.Font.

    Metrics are reported in the Hershey em box so that `style.Palette`,
    `hershey.layout_runs` and everything else above can treat the two kinds of
    font interchangeably.
    """

    def __init__(self, name: str = "DancingScript", weight: int | None = None) -> None:
        self.name = name
        path = FONT_DIR / f"{name}.ttf"
        self._font = ImageFont.truetype(str(path), RASTER_PX)
        if weight is not None:
            # Dancing Script ships as a variable font; without this it renders
            # at its lightest, which thins to a broken skeleton.
            try:
                self._font.set_variation_by_axes([float(weight)])
            except (OSError, AttributeError):
                pass
        ascent, descent = self._font.getmetrics()
        self._px_per_unit = (ascent + descent) / UNITS_PER_EM
        self._baseline_px = ascent

    # -- metrics ---------------------------------------------------------

    def _advance_px(self, text: str) -> float:
        return self._font.getlength(text)

    def advance(self, ch: str, scale: float) -> float:
        return self._advance_px(ch) / self._px_per_unit * scale

    def width(self, text: str, scale: float) -> float:
        return self._advance_px(text) / self._px_per_unit * scale

    # -- ink -------------------------------------------------------------

    def word(self, text: str, pen_x: float, baseline: float, scale: float) -> list[Polyline]:
        """Pen paths for a whole word, its left edge at pen_x on baseline."""
        paths = _skeleton(self, text)
        unit = scale / self._px_per_unit
        return [
            [(pen_x + x * unit, baseline + y * unit) for x, y in path]
            for path in paths
        ]

    def glyph(self, ch: str, pen_x: float, baseline: float, scale: float) -> list[Polyline]:
        return self.word(ch, pen_x, baseline, scale)


@lru_cache(maxsize=4096)
def _skeleton(font: Font, text: str) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Pen paths for one word in raster pixels, relative to origin on baseline.

    Cached because a reply reuses the same short words constantly and thinning
    is the one genuinely expensive step in the pipeline.
    """
    if not text.strip():
        return ()

    pad = 8
    width = max(1, int(font._advance_px(text)) + pad * 2)
    ascent, descent = font._font.getmetrics()
    height = ascent + descent + pad * 2

    canvas = Image.new("L", (width, height), 0)
    ImageDraw.Draw(canvas).text(
        (pad, pad), text, font=font._font, fill=255
    )

    mask = np.array(canvas) > 128
    if not mask.any():
        return ()

    paths = _stitch(_prune(_trace(thin(mask)), MIN_BRANCH_PX))

    out: list[tuple[tuple[float, float], ...]] = []
    for path in paths:
        trimmed = _simplify(path, SIMPLIFY_PX)
        if len(trimmed) < 2:
            continue
        # Back to an origin sitting on the baseline at the pen's start, which
        # is the coordinate space the layout code works in.
        out.append(
            tuple((x - pad, y - pad - ascent) for x, y in trimmed)
        )
    return tuple(out)
