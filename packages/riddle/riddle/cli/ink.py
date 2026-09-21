"""`riddle clear|write|picture|scene|testsheet`: everything that leaves a mark.

Every parser here is built with parents=[CONSENT], and nothing else is. That
is the list of commands that can put ink on a page, and it is one grep.
"""

from pathlib import Path

from riddle.cli import CONSENT, HOST


def add(sub) -> None:
    clear = sub.add_parser(
        "clear", parents=[CONSENT, HOST], help="eraser-sweep the visible page"
    )
    clear.set_defaults(run=lambda a: _tool("clear_page", a))

    write = sub.add_parser(
        "write",
        parents=[CONSENT, HOST],
        help="preview the diary's hand to a png; --yes writes it on the page",
    )
    write.add_argument("text", nargs="?", default=None)
    write.add_argument("--height", type=float, default=None, metavar="PX")
    write.add_argument("-o", "--out", type=Path, default=None)
    write.set_defaults(run=lambda a: _tool("handwriting", a))

    picture = sub.add_parser(
        "picture", parents=[CONSENT, HOST], help="draw a line-art image on the tablet"
    )
    picture.add_argument("image", type=Path)
    picture.add_argument("--width", type=int, default=760)
    picture.add_argument("--clear", action="store_true", help="wipe the page first")
    picture.set_defaults(run=lambda a: _tool("picture", a))

    scene = sub.add_parser(
        "scene", parents=[CONSENT, HOST], help="a flowchart and a snake: exercises the pen"
    )
    scene.set_defaults(run=lambda a: _tool("scene", a))

    sheet = sub.add_parser(
        "testsheet",
        parents=[CONSENT, HOST],
        help="calibration ladders: line gap, type size, hatch, radius",
    )
    sheet.set_defaults(run=lambda a: _tool("testsheet", a))


def _tool(name: str, args) -> int:
    from importlib import import_module

    return import_module(f"riddle.tools.{name}").run(args)
