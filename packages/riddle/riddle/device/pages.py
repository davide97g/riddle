"""Noticing that the writer has turned the page.

The conversation is Claude Code's resumed session, and it is cheap and
disposable: turn to a fresh page and the diary should start again, with no
idea what the last page said. Watching for that is this module's whole job,
and it is done over ssh against xochitl's own files, because there is no
other way to ask what page is open.

The other kind of remembering -- the handful of lines that survive a reset --
is a flat file and has nothing to do with the device. It lives in
`riddle.mind.memory`.
"""

import subprocess
import time

from riddle.device.ssh import XOCHITL_DIR as DATA_DIR

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
