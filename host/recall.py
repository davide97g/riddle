"""What the diary keeps when the conversation does not.

Two different kinds of remembering live here, and they are deliberately not
the same thing.

The *conversation* is Claude Code's resumed session, and it is cheap and
disposable: turn to a fresh page and it should start again, with no idea what
the last page said. That is what `Page` watches for.

*Memory* is the handful of things worth surviving that reset -- a name, a
promise, something the writer let slip. It lives in a plain file the model is
handed on every new conversation, so a diary that has been reset still knows
who it is talking to.
"""

import subprocess
import time
from datetime import datetime
from pathlib import Path

DATA_DIR = "/home/root/.local/share/remarkable/xochitl"

# The newest page file on the device, as "<mtime> <bytes> <doc>/<page>.rm".
# xochitl only flushes a page when you navigate away from it, so this lags
# what is on screen -- which is exactly the moment we care about, since
# turning to another page is what flushes the one you left.
_NEWEST_PAGE = (
    f"cd {DATA_DIR} 2>/dev/null && "
    'for f in */*.rm; do [ -e "$f" ] || continue; stat -c "%Y %s %n" "$f"; done '
    "| sort -rn | head -n 1"
)

# A page that loses this much of itself has been cleared rather than edited.
SHRINK_RATIO = 0.5


class Page:
    """Notices when the writer has moved to a different or emptied page.

    Detection is by the page's own file: a new name means a new page or a new
    notebook, and a sharp drop in size means the page was wiped. Both should
    cost the diary its memory of the conversation, because both mean the
    writer has drawn a line under whatever was being discussed.
    """

    def __init__(self, host: str) -> None:
        self.host = host
        self.name = ""
        self.size = 0
        self.look()

    def _read(self) -> tuple[str, int] | None:
        try:
            done = subprocess.run(
                ["ssh", self.host, _NEWEST_PAGE],
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        parts = done.stdout.split()
        if len(parts) != 3:
            return None
        return parts[2], int(parts[1])

    def look(self) -> str | None:
        """Check the device; return why the conversation should end, or None."""
        seen = self._read()
        if seen is None:
            return None
        name, size = seen

        was_name, was_size = self.name, self.size
        self.name, self.size = name, size

        if not was_name:
            return None
        if name != was_name:
            return "a different page"
        if was_size and size < was_size * SHRINK_RATIO:
            return "the page was cleared"
        return None


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


def watch(page: Page, on_reset, busy=None, interval: float = 12.0) -> None:
    """Poll the device forever, calling on_reset(reason) when the page turns.

    `busy` says the diary is mid-turn. That matters because answering means
    erasing the page and writing over it, which looks exactly like the writer
    wiping it: without this the diary would forget the conversation every time
    it finished a sentence. While busy we only re-baseline, so its own work
    never reads as the writer turning the page.
    """
    while True:
        time.sleep(interval)
        if busy is not None and busy():
            page.look()
            continue
        reason = page.look()
        if reason:
            on_reset(reason)
