"""Page-wide operations.

xochitl's own "erase all" sits behind a toolbar we cannot press, so clearing
a page means doing it the way a person would: broad rubber strokes, edge to
edge.
"""

import draw
from geometry import SCREEN_H, SCREEN_W

SWEEP_SPACING = 26  # a little under the eraser's width, so passes overlap


def sweep(spacing: float = SWEEP_SPACING) -> list[draw.Polyline]:
    rows: list[draw.Polyline] = []
    y = 10.0
    rightward = True
    while y < SCREEN_H:
        span = [(6.0, y), (SCREEN_W - 6.0, y)]
        rows.append(span if rightward else span[::-1])
        rightward = not rightward
        y += spacing
    return rows
