"""Vector primitives for anything the tablet should draw that is not text.

Everything the diary puts on the page is a pen stroke, so every shape here is
just a polyline in screen coordinates. There are no fills: a solid area has to
be hatched, the way you would shade it by hand.
"""

import math

Point = tuple[float, float]
Polyline = list[Point]


def line(a: Point, b: Point) -> Polyline:
    return [a, b]


def polyline(points: list[Point], close: bool = False) -> Polyline:
    return list(points) + ([points[0]] if close and points else [])


def rect(x: float, y: float, w: float, h: float) -> Polyline:
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]


def rounded_rect(x: float, y: float, w: float, h: float, r: float = 18) -> Polyline:
    r = min(r, w / 2, h / 2)
    pts: Polyline = []
    corners = [
        (x + w - r, y + r, -90, 0),
        (x + w - r, y + h - r, 0, 90),
        (x + r, y + h - r, 90, 180),
        (x + r, y + r, 180, 270),
    ]
    for cx, cy, start, end in corners:
        for step in range(9):
            angle = math.radians(start + (end - start) * step / 8)
            pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    pts.append(pts[0])
    return pts


def ellipse(cx: float, cy: float, rx: float, ry: float, steps: int = 48) -> Polyline:
    return [
        (cx + rx * math.cos(2 * math.pi * i / steps), cy + ry * math.sin(2 * math.pi * i / steps))
        for i in range(steps + 1)
    ]


def circle(cx: float, cy: float, r: float, steps: int = 48) -> Polyline:
    return ellipse(cx, cy, r, r, steps)


def arc(cx: float, cy: float, r: float, start_deg: float, end_deg: float, steps: int = 24) -> Polyline:
    return [
        (
            cx + r * math.cos(math.radians(start_deg + (end_deg - start_deg) * i / steps)),
            cy + r * math.sin(math.radians(start_deg + (end_deg - start_deg) * i / steps)),
        )
        for i in range(steps + 1)
    ]


def bezier(p0: Point, p1: Point, p2: Point, p3: Point, steps: int = 24) -> Polyline:
    out = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        out.append(
            (
                u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
            )
        )
    return out


def arrow(a: Point, b: Point, head: float = 20, spread: float = 0.42) -> list[Polyline]:
    angle = math.atan2(b[1] - a[1], b[0] - a[0])
    barbs = [
        [
            b,
            (
                b[0] - head * math.cos(angle + sign * spread),
                b[1] - head * math.sin(angle + sign * spread),
            ),
        ]
        for sign in (1, -1)
    ]
    return [line(a, b), *barbs]


def hatch(
    x: float, y: float, w: float, h: float, spacing: float = 14, angle_deg: float = 45
) -> list[Polyline]:
    """Shade a rectangle with parallel strokes, clipped to the rectangle."""
    angle = math.radians(angle_deg)
    dx, dy = math.cos(angle), math.sin(angle)
    span = abs(w * dy) + abs(h * dx)
    lines = []
    offset = -span / 2
    cx, cy = x + w / 2, y + h / 2
    while offset <= span / 2:
        # Walk a long line through the centre, offset perpendicular, and clip.
        px, py = cx - dy * offset, cy + dx * offset
        far = w + h
        segment = _clip((px - dx * far, py - dy * far), (px + dx * far, py + dy * far), x, y, w, h)
        if segment:
            lines.append(list(segment))
        offset += spacing
    return lines


def _clip(a: Point, b: Point, x: float, y: float, w: float, h: float) -> tuple[Point, Point] | None:
    """Liang-Barsky clip of a segment against an axis-aligned box."""
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] - x), (dx, x + w - a[0]), (-dy, a[1] - y), (dy, y + h - a[1])):
        if p == 0:
            if q < 0:
                return None
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return None
    return (a[0] + t0 * dx, a[1] + t0 * dy), (a[0] + t1 * dx, a[1] + t1 * dy)


def translate(strokes: list[Polyline], dx: float, dy: float) -> list[Polyline]:
    return [[(x + dx, y + dy) for x, y in stroke] for stroke in strokes]


def scale(strokes: list[Polyline], factor: float, origin: Point = (0, 0)) -> list[Polyline]:
    ox, oy = origin
    return [
        [(ox + (x - ox) * factor, oy + (y - oy) * factor) for x, y in stroke]
        for stroke in strokes
    ]


def plot(
    fn, x0: float, x1: float, box: tuple[float, float, float, float], samples: int = 120
) -> Polyline:
    """Sample a function and fit it into a screen-space box."""
    xs = [x0 + (x1 - x0) * i / samples for i in range(samples + 1)]
    ys = [fn(x) for x in xs]
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or 1
    bx, by, bw, bh = box
    return [
        (bx + bw * (x - x0) / (x1 - x0), by + bh * (1 - (y - lo) / span))
        for x, y in zip(xs, ys)
    ]
