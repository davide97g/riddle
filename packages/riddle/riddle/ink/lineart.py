"""Convert black-and-white line art into pen strokes.

Contour tracing is wrong for this kind of picture: every drawn line has
thickness, so tracing its edges would ink each line twice, once down each
side. Instead the ink is split in two. Anything thin is thinned to its
centreline and drawn as a single stroke, the way it was drawn originally;
anything solid enough to be a fill keeps its outline and gets shaded with
hatching, since the tablet has no way to lay down a black area.
"""

from pathlib import Path

from PIL import Image, ImageOps

from riddle.ink import image as contours

Point = tuple[float, float]
Polyline = list[Point]


def render(
    source: Path,
    width: int = 420,
    threshold: int = 128,
    fill_depth: int = 4,
    hatch_spacing: int = 5,
    cross_hatch: bool = False,
    min_length: float = 3.0,
    epsilon: float = 0.7,
) -> list[Polyline]:
    """Return strokes in a 0..1 by 0..1 space, ready to be placed on a page."""
    ink, w, h = _load(source, width, threshold)

    solid = _erode(ink, w, h, fill_depth)
    thin = [a and not b for a, b in zip(ink, _dilate(solid, w, h, max(1, fill_depth - 1)))]

    strokes: list[Polyline] = []
    strokes += _outline_and_shade(solid, w, h, hatch_spacing, cross_hatch)
    strokes += _centrelines(thin, w, h, min_length, epsilon)

    return [[(x / (w - 1), y / (h - 1)) for x, y in stroke] for stroke in strokes]


def place(strokes: list[Polyline], box: tuple[float, float, float, float]) -> list[Polyline]:
    """Fit into a box, preserving aspect and centring what is left over."""
    x, y, bw, bh = box
    points = [p for s in strokes for p in s]
    if not points:
        return []
    ratio = max((p[1] for p in points)) or 1
    scale = min(bw, bh / ratio)
    ox = x + (bw - scale) / 2
    oy = y + (bh - scale * ratio) / 2
    return [[(ox + px * scale, oy + py * scale) for px, py in s] for s in strokes]


def _load(source: Path, width: int, threshold: int) -> tuple[list[bool], int, int]:
    img = Image.open(source)
    if img.mode == "RGBA":  # stickers arrive on transparency, not on white
        flat = Image.new("RGB", img.size, "white")
        flat.paste(img, mask=img.split()[3])
        img = flat
    img = ImageOps.autocontrast(img.convert("L"))
    height = max(1, round(img.height * width / img.width))
    img = img.resize((width, height), Image.LANCZOS)
    data = list(img.getdata())
    return [v < threshold for v in data], width, height


def _neighbours(index: int, w: int, h: int) -> list[int]:
    x, y = index % w, index // w
    out = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h:
                out.append(ny * w + nx)
    return out


def _erode(mask: list[bool], w: int, h: int, times: int) -> list[bool]:
    current = mask
    for _ in range(times):
        nxt = [False] * len(current)
        for i, on in enumerate(current):
            if on and all(current[n] for n in _neighbours(i, w, h)):
                nxt[i] = True
        current = nxt
    return current


def _dilate(mask: list[bool], w: int, h: int, times: int) -> list[bool]:
    current = mask
    for _ in range(times):
        nxt = list(current)
        for i, on in enumerate(current):
            if on:
                for n in _neighbours(i, w, h):
                    nxt[n] = True
        current = nxt
    return current


def _outline_and_shade(
    solid: list[bool], w: int, h: int, spacing: int, cross: bool = False
) -> list[Polyline]:
    if not any(solid):
        return []
    grid = [[255 if solid[y * w + x] else 0 for x in range(w)] for y in range(h)]
    strokes = [
        path
        for path in _contour_paths(grid, w, h, 128)
        if len(path) > 8
    ]
    # Shade by walking lines across the mask and keeping the spans inside it.
    # A solid area cannot be inked solid, so the spacing is what decides
    # whether it reads as black or as a cage.
    strokes += _spans(solid, w, h, spacing, vertical=False)
    if cross:
        strokes += _spans(solid, w, h, spacing, vertical=True)
    return strokes


def _spans(
    solid: list[bool], w: int, h: int, spacing: int, vertical: bool
) -> list[Polyline]:
    out: list[Polyline] = []
    outer, inner = (w, h) if vertical else (h, w)
    for a in range(0, outer, spacing):
        start = None
        for b in range(inner):
            index = b * w + a if vertical else a * w + b
            if solid[index] and start is None:
                start = b
            elif not solid[index] and start is not None:
                if b - start > 1:
                    out.append(
                        [(a, start), (a, b - 1)] if vertical else [(start, a), (b - 1, a)]
                    )
                start = None
        if start is not None and inner - start > 1:
            out.append(
                [(a, start), (a, inner - 1)] if vertical else [(start, a), (inner - 1, a)]
            )
    return out


def _contour_paths(grid, w: int, h: int, level: int) -> list[Polyline]:
    return [contours._simplify(p, 0.6) for p in contours._contours(grid, w, h, level)]


# Zhang-Suen thinning, which peels a shape down to a one pixel wide skeleton
# while keeping it connected.
def _thin(mask: list[bool], w: int, h: int) -> list[bool]:
    pixels = list(mask)
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            doomed = []
            for y in range(1, h - 1):
                for x in range(1, w - 1):
                    i = y * w + x
                    if not pixels[i]:
                        continue
                    p = [
                        pixels[i - w], pixels[i - w + 1], pixels[i + 1], pixels[i + w + 1],
                        pixels[i + w], pixels[i + w - 1], pixels[i - 1], pixels[i - w - 1],
                    ]
                    count = sum(p)
                    if count < 2 or count > 6:
                        continue
                    transitions = sum(
                        1 for k in range(8) if not p[k] and p[(k + 1) % 8]
                    )
                    if transitions != 1:
                        continue
                    if step == 0:
                        if (p[0] and p[2] and p[4]) or (p[2] and p[4] and p[6]):
                            continue
                    else:
                        if (p[0] and p[2] and p[6]) or (p[0] and p[4] and p[6]):
                            continue
                    doomed.append(i)
            if doomed:
                changed = True
                for i in doomed:
                    pixels[i] = False
    return pixels


def _centrelines(
    mask: list[bool], w: int, h: int, min_length: float, epsilon: float
) -> list[Polyline]:
    skeleton = _thin(mask, w, h)
    ink = {i for i, on in enumerate(skeleton) if on}
    degree = {i: [n for n in _neighbours(i, w, h) if n in ink] for i in ink}

    unvisited = set(ink)
    paths: list[Polyline] = []

    def walk(start: int) -> list[int]:
        path = [start]
        unvisited.discard(start)
        while True:
            nxt = next((n for n in degree[path[-1]] if n in unvisited), None)
            if nxt is None:
                return path
            unvisited.discard(nxt)
            path.append(nxt)

    # Start at loose ends so strokes run the way a pen would draw them, then
    # mop up whatever closed loops are left over.
    for start in sorted(ink, key=lambda i: len(degree[i])):
        if start in unvisited and len(degree[start]) != 2:
            paths.append(walk(start))
    while unvisited:
        paths.append(walk(next(iter(unvisited))))

    out = []
    for path in paths:
        points: Polyline = [(i % w, i // w) for i in path]
        if _length(points) < min_length:
            continue
        out.append(contours._simplify(points, epsilon))
    return out


def _length(path: Polyline) -> float:
    return sum(
        ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 for a, b in zip(path, path[1:])
    )
