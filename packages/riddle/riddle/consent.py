"""Ask before touching the tablet.

Two capabilities, kept apart. Drawing puts ink in whatever notebook happens
to be open -- there is no way to ask xochitl which page that is, so the
diary announces its intent and otherwise never draws unprompted. Reading the
screen means reading another process's address space over ssh. They are
different risks and they keep different switches: someone running the loop
headless wants standing permission to draw without also granting screen
reads, and a monitoring script that photographs the page must not thereby be
allowed to write on it.

What is shared is the implementation, which used to exist twice with
different wording in two places.

`yes` is keyword-only and has no default, and nothing here looks at
`sys.argv`. That is deliberate. The old gate sniffed the raw argument list,
which meant an argument parser in front of it could quietly defeat it, and
meant `riddle write "--yes is a strange thing to write"` authorised itself.
Now the flag is parsed once, declared on the one shared parent parser, and
passed in; a caller that forgets fails loudly at the call site, where a
reviewer is already looking.
"""

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    key: str
    env: str
    refusal: str
    announce: bool


DRAW = Action(
    "draw",
    "RIDDLE_ALLOW_DRAW",
    "open {notebook!r} on the tablet, then rerun with --yes",
    announce=True,
)

SCREEN = Action(
    "screen",
    "RIDDLE_ALLOW_SNAP",
    "rerun with --yes, or set RIDDLE_ALLOW_SNAP=1",
    announce=False,
)


def require(action: Action, what: str, *, yes: bool) -> None:
    """Refuse `what` unless someone has just said it is safe. Exits if not."""
    from riddle import config

    cfg = config.get()
    standing = cfg.allow_draw if action is DRAW else cfg.allow_snap
    if yes or standing:
        if action.announce:
            print(
                f"{what} -> whatever notebook is open "
                f"(expecting {cfg.notebook!r})"
            )
        return
    sys.exit(f"refusing to {what}: {action.refusal.format(notebook=cfg.notebook)}")


def draw(what: str, *, yes: bool) -> None:
    require(DRAW, what, yes=yes)


def screen(what: str = "read the screen", *, yes: bool) -> None:
    require(SCREEN, what, yes=yes)
