"""Turn captured pen strokes into a PNG the model can read."""

from pathlib import Path

from PIL import Image, ImageDraw

from geometry import SCREEN_H, SCREEN_W

MARGIN = 40
MAX_WIDTH = 1000


def strokes_to_png(strokes: list[list[tuple[float, float]]], path: Path) -> Path:
    """Render screen-space strokes, cropped to what was written."""
    image = Image.new("L", (SCREEN_W, SCREEN_H), 255)
    draw = ImageDraw.Draw(image)
    for stroke in strokes:
        if len(stroke) == 1:
            x, y = stroke[0]
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=0)
        elif stroke:
            draw.line([(x, y) for x, y in stroke], fill=0, width=4, joint="curve")

    box = bounding_box(strokes)
    if box:
        x0, y0, x1, y1 = box
        image = image.crop(
            (
                max(0, int(x0) - MARGIN),
                max(0, int(y0) - MARGIN),
                min(SCREEN_W, int(x1) + MARGIN),
                min(SCREEN_H, int(y1) + MARGIN),
            )
        )
    if image.width > MAX_WIDTH:
        ratio = MAX_WIDTH / image.width
        image = image.resize((MAX_WIDTH, max(1, int(image.height * ratio))))

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def bounding_box(
    strokes: list[list[tuple[float, float]]]
) -> tuple[float, float, float, float] | None:
    points = [p for stroke in strokes for p in stroke]
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)
