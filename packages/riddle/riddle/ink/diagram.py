"""Box-and-arrow diagrams, drawn as pen strokes.

Labels use the plain Hershey hand, since a diagram is read rather than
admired, and the cursive one costs legibility at small sizes.
"""

import math
from dataclasses import dataclass, field

from riddle.ink import draw
from riddle.ink.hershey import Font, Run, layout_runs

Polyline = draw.Polyline

_LABEL_FONT = Font("futural")


@dataclass
class Node:
    key: str
    label: str
    x: float
    y: float
    w: float = 300
    h: float = 110
    shape: str = "box"  # box | round | ellipse
    text_height: float = 34

    @property
    def center(self) -> draw.Point:
        return (self.x + self.w / 2, self.y + self.h / 2)

    def outline(self) -> Polyline:
        if self.shape == "ellipse":
            return draw.ellipse(*self.center, self.w / 2, self.h / 2)
        if self.shape == "round":
            return draw.rounded_rect(self.x, self.y, self.w, self.h)
        return draw.rect(self.x, self.y, self.w, self.h)

    def text(self) -> list[Polyline]:
        runs = [Run(self.label, _LABEL_FONT, self.text_height)]
        rows = max(1, _rows(runs, self.w - 40))
        block = (rows - 1) * self.text_height * 1.6
        baseline = self.center[1] + self.text_height * 0.32 - block / 2
        return layout_runs(
            runs,
            center_x=self.center[0],
            baseline=baseline,
            max_width=self.w - 40,
            line_gap=1.6,
        )


def _rows(runs: list[Run], max_width: float) -> int:
    from hershey import line_count

    return line_count(runs, max_width)


@dataclass
class Diagram:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[tuple[str, str, str]] = field(default_factory=list)

    def add(self, node: Node) -> Node:
        self.nodes[node.key] = node
        return node

    def connect(self, a: str, b: str, label: str = "") -> None:
        self.edges.append((a, b, label))

    def strokes(self) -> list[Polyline]:
        out: list[Polyline] = []
        for node in self.nodes.values():
            out.append(node.outline())
            out.extend(node.text())
        for a, b, label in self.edges:
            start, end = _edge_points(self.nodes[a], self.nodes[b])
            out.extend(draw.arrow(start, end))
            if label:
                mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2 - 12)
                out.extend(
                    layout_runs(
                        [Run(label, _LABEL_FONT, 26)],
                        center_x=mid[0],
                        baseline=mid[1],
                        max_width=400,
                    )
                )
        return out


def _edge_points(a: Node, b: Node) -> tuple[draw.Point, draw.Point]:
    """Meet each box on its border rather than at its centre."""
    ax, ay = a.center
    bx, by = b.center
    angle = math.atan2(by - ay, bx - ax)
    return _border(a, angle), _border(b, angle + math.pi)


def _border(node: Node, angle: float) -> draw.Point:
    cx, cy = node.center
    dx, dy = math.cos(angle), math.sin(angle)
    if node.shape == "ellipse":
        return (cx + dx * node.w / 2, cy + dy * node.h / 2)
    scale = min(
        node.w / 2 / abs(dx) if dx else float("inf"),
        node.h / 2 / abs(dy) if dy else float("inf"),
    )
    return (cx + dx * scale, cy + dy * scale)
