"""Turn a bitmap into pen strokes.

The tablet can only be given lines, so a photograph has to become line art
before it can be drawn. Tracing brightness contours gives a topographic sort
of portrait that survives being reduced to a few hundred pen strokes, which
is roughly the budget before a drawing takes longer than anyone will watch.
"""

from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

Point = tuple[float, float]
Polyline = list[Point]


def trace(
    source: Path,
    levels: tuple[int, ...] = (60, 100, 140, 180, 215),
    width: int = 240,
    smooth: float = 1.0,
    min_length: float = 5.0,
    epsilon: float = 0.5,
) -> list[Polyline]:
    """Trace brightness contours, in a 0..1 by 0..1 coordinate space."""
    image = Image.open(source).convert("L")
    image = ImageOps.autocontrast(image)
    height = max(1, round(image.height * width / image.width))
    image = image.resize((width, height), Image.LANCZOS)
    if smooth:
        image = image.filter(ImageFilter.GaussianBlur(smooth))

    pixels = list(image.getdata())
    grid = [pixels[row * width : (row + 1) * width] for row in range(height)]

    strokes: list[Polyline] = []
    for level in levels:
        for path in _contours(grid, width, height, level):
            # Judge a contour by how far it runs, not by how many points it
            # needs: simplifying first would throw away long straight edges.
            if _length(path) < min_length:
                continue
            simple = _simplify(path, epsilon)
            strokes.append([(x / (width - 1), y / (height - 1)) for x, y in simple])
    return strokes


def _length(path: Polyline) -> float:
    return sum(
        ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        for a, b in zip(path, path[1:])
    )


def place(
    strokes: list[Polyline], box: tuple[float, float, float, float]
) -> list[Polyline]:
    """Fit normalised strokes into a screen-space box, keeping aspect."""
    x, y, w, h = box
    return [[(x + px * w, y + py * h) for px, py in stroke] for stroke in strokes]


def _contours(grid, width: int, height: int, level: int) -> list[Polyline]:
    """Marching squares: collect iso-level segments, then join them up."""
    segments: list[tuple[Point, Point]] = []
    for row in range(height - 1):
        for col in range(width - 1):
            a = grid[row][col]
            b = grid[row][col + 1]
            c = grid[row + 1][col + 1]
            d = grid[row + 1][col]
            index = (a > level) | ((b > level) << 1) | ((c > level) << 2) | ((d > level) << 3)
            if index in (0, 15):
                continue
            top = (col + _lerp(a, b, level), row)
            right = (col + 1, row + _lerp(b, c, level))
            bottom = (col + _lerp(d, c, level), row + 1)
            left = (col, row + _lerp(a, d, level))
            for pair in _CASES[index]:
                edges = {"t": top, "r": right, "b": bottom, "l": left}
                segments.append((edges[pair[0]], edges[pair[1]]))
    return _join(segments)


def _lerp(a: int, b: int, level: int) -> float:
    if a == b:
        return 0.5
    return min(1.0, max(0.0, (level - a) / (b - a)))


# Which edges each marching-squares case connects.
_CASES: dict[int, tuple[str, ...]] = {
    1: ("lt",), 2: ("tr",), 3: ("lr",), 4: ("rb",), 5: ("lt", "rb"),
    6: ("tb",), 7: ("lb",), 8: ("bl",), 9: ("tb",), 10: ("tl", "br"),
    11: ("br",), 12: ("rl",), 13: ("rt",), 14: ("tl",),
}


def _join(segments: list[tuple[Point, Point]], tol: float = 0.02) -> list[Polyline]:
    """Chain segments that share an endpoint into continuous paths.

    Marching squares emits each segment with its own orientation, so the walk
    has to treat the links as undirected and be able to run either way out of
    a point.
    """

    def key(p: Point) -> tuple[int, int]:
        return (round(p[0] / tol), round(p[1] / tol))

    at: dict[tuple[int, int], list[int]] = {}
    for index, (a, b) in enumerate(segments):
        at.setdefault(key(a), []).append(index)
        at.setdefault(key(b), []).append(index)

    used = [False] * len(segments)

    def walk(index: int, forward: bool) -> Polyline:
        a, b = segments[index]
        path = [a, b] if forward else [b, a]
        while True:
            here = key(path[-1])
            nxt = next((i for i in at.get(here, []) if not used[i]), None)
            if nxt is None:
                return path
            used[nxt] = True
            x, y = segments[nxt]
            path.append(y if key(x) == here else x)

    paths: list[Polyline] = []
    for index in range(len(segments)):
        if used[index]:
            continue
        used[index] = True
        tail = walk(index, True)
        head = walk(index, False)
        # walk() replays the seed segment in both directions; drop one copy.
        paths.append(head[::-1][:-2] + tail)
    return paths


def _simplify(path: Polyline, epsilon: float) -> Polyline:
    """Ramer-Douglas-Peucker, so straight runs cost one stroke segment."""
    if len(path) < 3:
        return path
    ax, ay = path[0]
    bx, by = path[-1]
    dx, dy = bx - ax, by - ay
    norm = (dx * dx + dy * dy) ** 0.5
    worst, index = 0.0, 0
    for i in range(1, len(path) - 1):
        px, py = path[i]
        if norm == 0:
            distance = ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
        else:
            distance = abs(dy * px - dx * py + bx * ay - by * ax) / norm
        if distance > worst:
            worst, index = distance, i
    if worst <= epsilon:
        return [path[0], path[-1]]
    return _simplify(path[: index + 1], epsilon)[:-1] + _simplify(path[index:], epsilon)
