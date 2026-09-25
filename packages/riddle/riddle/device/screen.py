"""Read what is actually on the tablet's screen.

There is no framebuffer to read. rm2fb is a Qt5 shim and xochitl is Qt6, so
the supported route does not exist on this firmware. What does work is cruder:
xochitl maps /dev/fb0 and then keeps the buffer it actually paints in an
anonymous mapping directly after it, and /proc/<pid>/mem can be read over ssh.

Firmware 3.24 moved that buffer from gray16 to 32-bit BGRA, so the pixel
format below is pinned rather than detected. Detection is what reSnap does and
it does not work here: this tablet's /etc/os-release reports the Codex Linux
version (5.8.203), not xochitl's 3.28, so a version test picks the old format
and returns noise. The map size check is the honest guard instead -- a layout
change fails loudly rather than handing back a picture of nothing.

Nothing here touches the riddled pipe. It is its own ssh connection, which is
what lets it be called from a thread or a process that does not own the device.
"""

import gzip
import io
import subprocess

from PIL import Image

FB_W, FB_H, BPP = 1404, 1872, 4

# The painted frame starts 468 lines and 336 pixels into the mapping. Worked
# out by davisremmel and carried by reSnap; it happens to be exactly 642 pages,
# so the read below can stay on page boundaries and skip with dd's fast path.
SKIP = 2629632
BYTES = FB_W * FB_H * BPP
PAGES = -(-BYTES // 4096)

from riddle.device.ssh import BASE as SSH_OPTIONS

# Where the painted frame is depends on the xochitl process, not only on the
# firmware. Most starts put it inside the anonymous mapping right after
# /dev/fb0, SKIP bytes in -- the layout reSnap carries. Some starts do not:
# after a restart on 3.28 that mapping was 3MB, and the frame was a mapping
# of its own, exactly PAGES long, sixty-five entries further on, starting at
# its first byte. Other screen-sized mappings exist too -- xochitl's page
# caches, tiled at other widths -- but they sit before /dev/fb0 or are a page
# longer, so the rule is: the known layout if it fits, else the nearest
# anonymous rw mapping after /dev/fb0 of exactly the frame's size. Found once
# per connection, since a restart is also a new pid and a redial.
#
# busybox on the tablet: no pidof -s, no python, no lz4, no strtonum in awk,
# so the maps are walked in sh. gzip -1 takes the 10.5MB frame down to about
# 36KB in half a second, which is far cheaper than sending it raw.
_FIND = (
    'PID=$(pidof xochitl | cut -d" " -f1); '
    '[ -n "$PID" ] || { echo "xochitl not running" >&2; exit 1; }; '
    'MAPS=/proc/$PID/maps; '
    'AT=$(grep -n /dev/fb0 $MAPS | head -n1 | cut -d: -f1); '
    '[ -n "$AT" ] || { echo "xochitl has no /dev/fb0 mapped" >&2; exit 2; }; '
    'MAP=$(sed -n "$((AT + 1))p" $MAPS); '
    'BASE=${MAP%%%%-*}; END=${MAP#*-}; END=${END%%%% *}; '
    'if [ $(( 0x$END - 0x$BASE )) -ge %(near)d ]; then '
    'OFF=$(( 0x$BASE + %(skip)d )); '
    'else '
    'OFF=$(tail -n +$((AT + 1)) $MAPS | while read R P X D I N; do '
    '[ "$P" = rw-p ] && [ -z "$N" ] || continue; '
    'S=$(( 0x${R#*-} - 0x${R%%%%-*} )); '
    '[ $S -eq %(size)d ] && { echo $(( 0x${R%%%%-*} )); break; }; '
    'done); '
    'fi; '
    '[ -n "$OFF" ] || { echo "no painted frame in xochitl; firmware layout changed" >&2; exit 2; }; '
) % {"near": SKIP + BYTES, "skip": SKIP, "size": PAGES * 4096}
_READ = (
    "dd if=/proc/$PID/mem bs=4096 skip=$(( OFF / 4096 )) "
    "count=%d 2>/dev/null | gzip -1 -c"
) % PAGES

REMOTE = _FIND + _READ

# The same read on one long-lived connection, one frame per line on stdin.
# The host paces it rather than a `sleep` over there, so there is never more
# than one frame in flight, and a host that stops asking costs the tablet
# nothing. Each frame is its own gzip member, which is the framing: the
# stream needs no length prefix and the tablet writes no temporary file. A
# restarted xochitl leaves $PID stale, dd reads nothing, and the empty member
# that comes back is a short frame the host rejects and redials.
STREAM = _FIND + "while read x; do " + _READ + "; done"


def grab(host: str = "rm2", timeout: int = 30) -> Image.Image:
    """The visible screen, as greyscale, the way a photograph of it would look.

    The frame is torn: nothing here synchronises with xochitl's painting, so a
    stroke being drawn as this runs can come out half finished. That is fine
    for a page of handwriting and wrong for anything moving.
    """
    done = subprocess.run(
        ["ssh", *SSH_OPTIONS, host, REMOTE], capture_output=True, timeout=timeout
    )
    if done.returncode != 0:
        raise RuntimeError(done.stderr.decode().strip() or "could not read the screen")

    return frame(gzip.decompress(done.stdout))


def frame(raw: bytes) -> Image.Image:
    """One decompressed read of the painted buffer, as greyscale."""
    if len(raw) < BYTES:
        raise RuntimeError(f"short read: {len(raw)} of {BYTES} bytes")

    # The panel is BGRA and the alpha byte is not meaningful, so the channels
    # are reordered rather than converted; going straight to "L" through RGBA
    # would weight the wrong ones.
    b, g, r, _ = Image.frombytes("RGBA", (FB_W, FB_H), raw[:BYTES]).split()
    return Image.merge("RGB", (r, g, b)).convert("L")


def png(host: str = "rm2", scale: float = 1.0, timeout: int = 30) -> bytes:
    """The screen as PNG bytes, for handing to something that wants a picture."""
    shot = grab(host, timeout)
    if scale != 1.0:
        size = (round(FB_W * scale), round(FB_H * scale))
        shot = shot.resize(size, Image.LANCZOS)
    buf = io.BytesIO()
    shot.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
