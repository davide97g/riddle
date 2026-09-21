"""The handful of things the diary keeps when the conversation does not.

Turning the page costs the diary its resumed session, and that is meant to
hurt as little as possible: the conversation is disposable. What is not
disposable is the odd line worth surviving the reset -- a name, a promise,
something the writer let slip. The model ends a reply with `REMEMBER: <line>`
and it lands here.

A plain file on purpose. It outlives the store, whose schema keeps changing
and which is safe to delete; you can read it, edit it and back it up without
this code. `riddle.device.pages` is the other half of remembering, and has
nothing to do with this one.
"""

from datetime import datetime
from pathlib import Path


class Memory:
    """The lines the diary chose to keep, in a file it is read back from."""

    def __init__(self, path: Path, limit: int = 40) -> None:
        self.path = path
        self.limit = limit

    def lines(self) -> list[str]:
        if not self.path.exists():
            return []
        return [
            line.strip()
            for line in self.path.read_text().splitlines()
            if line.strip()
        ]

    def text(self) -> str:
        return "\n".join(self.lines())

    def keep(self, note: str) -> None:
        """Append one thing worth remembering, oldest dropped past the limit."""
        note = " ".join(note.split())
        if not note:
            return
        kept = self.lines()
        stamped = f"[{datetime.now():%Y-%m-%d}] {note}"
        # Do not write the same thing twice; the model repeats itself across
        # turns and the file is fed back to it whole.
        if any(line.endswith(note) for line in kept):
            return
        kept.append(stamped)
        self.path.write_text("\n".join(kept[-self.limit :]) + "\n")
