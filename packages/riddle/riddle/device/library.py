"""Put a document in the tablet's library, the way xochitl would have.

The pen can only lay down lines, so a picture drawn with it is a tracing of
a picture. xochitl can do much better on its own: it renders pdf and epub
natively, sharp at every zoom, and lets you write over them. So a file from
the page becomes a real document in the library rather than ink on the open
one.

There is no import api on this firmware. The USB web interface has an upload
form, but only on the cable's address, and the diary lives on wifi. What does
work is what xochitl itself does: the store is a flat directory of
`<uuid>.<ext>` beside a `<uuid>.metadata` and a `<uuid>.content`, and xochitl
reads it at startup. The fields written here mirror the tablet's own files
on 3.28; xochitl fills in everything else the first time it opens the
document.

**xochitl has to be stopped around the write.** It holds the store in memory
and rewrites it on exit -- the same reason `scripts/backup/restore.sh` stops
it -- so a file written under a running xochitl may be clobbered by its stale
copy on the way down. The restart is the cost: whatever is open on the tablet
closes, about ten seconds of the screen reloading, and the new document is in
the library to be opened by hand. Nothing here can open it for you.

Nothing is kept on this machine. The file is packed in memory and piped
straight into tar on the tablet.
"""

import io
import json
import re
import subprocess
import tarfile
import time
import uuid as uuids
from dataclasses import dataclass

from PIL import Image, ImageOps

from riddle.device.ssh import BASE as SSH_OPTIONS, XOCHITL_DIR

# The screen, in pixels and at its own density: 1404x1872 at 226 dpi.
SCREEN_W, SCREEN_H, DPI = 1404, 1872, 226
# Enough pixels for a two-times zoom to stay sharp, and no more: past that a
# photograph from a phone is megabytes the tablet renders down anyway.
LONG_MAX = SCREEN_H * 2

# One upload at most this big. Cloudflare's own ceiling is 100MB, and a pdf
# of that size is already slow to page through on the tablet.
MAX_BYTES = 64 << 20

# Stop, write, sync, start. xochitl comes back even when tar fails, so a bad
# upload costs a restart rather than a tablet with no interface on it.
REMOTE = (
    "systemctl stop xochitl || exit 3; "
    f"cd {XOCHITL_DIR} && tar -xf -; done=$?; "
    "sync; systemctl start xochitl; exit $done"
)


@dataclass
class Document:
    name: str
    kind: str          # "pdf" | "epub"
    body: bytes
    orientation: str   # "portrait" | "landscape"
    pages: int | None  # known for what was made here, not for what was passed through


def title(filename: str) -> str:
    """The name the library shows: the file's own, without its extension."""
    stem = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = re.sub(r"\.(pdf|epub|png|jpe?g|webp|gif|bmp|tiff?)$", "", stem, flags=re.I)
    stem = " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", stem).split())
    return stem[:120] or "Untitled"


def pack(data: bytes, name: str) -> Document:
    """Turn an upload into something xochitl renders natively.

    A pdf or an epub goes in exactly as it came: xochitl's renderer is better
    at its own formats than anything here would be. Anything else must be an
    image Pillow can read, and becomes a one-page pdf.
    """
    if not data:
        raise ValueError("the file is empty")
    if len(data) > MAX_BYTES:
        raise ValueError(f"the file is over {MAX_BYTES >> 20}MB")
    if data[:5] == b"%PDF-":
        return Document(name, "pdf", data, "portrait", None)
    # An epub is a zip whose first entry is an uncompressed `mimetype`.
    if data[:2] == b"PK" and b"application/epub+zip" in data[30:90]:
        return Document(name, "epub", data, "portrait", None)
    return _picture(data, name)


def _picture(data: bytes, name: str) -> Document:
    """One image as one page, laid out for a greyscale screen.

    - Turned the way the camera meant it: phones store a rotation flag
      rather than rotated pixels.
    - Transparency flattened onto white. Dropped straight to greyscale, a
      transparent png turns black, and a logo becomes a black rectangle.
    - Greyscale here rather than on the tablet: the panel shows no colour,
      and a third of the bytes is a third of the transfer.
    - The page is the picture's own shape, and a wide one is marked
      landscape, so xochitl turns the page rather than shrinking a wide
      picture to a strip across the middle of a tall screen.
    - Sized so its long side is the screen's at 226 dpi. xochitl fits the
      page to the screen either way, but a page of the screen's own
      physical size is what makes a zoom of 100% mean one pixel per pixel.
    """
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:  # noqa: BLE001 - Pillow raises a dozen types
        raise ValueError("not a pdf, an epub or an image this server can read") from exc

    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        image = image.convert("RGBA")
        paper = Image.new("RGBA", image.size, "white")
        image = Image.alpha_composite(paper, image)
    image = image.convert("L")

    long_side = max(image.size)
    if long_side > LONG_MAX:
        scale = LONG_MAX / long_side
        image = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
            Image.LANCZOS,
        )
        long_side = max(image.size)

    landscape = image.width > image.height
    # The page's long side is the screen's long side, in inches; `resolution`
    # is how Pillow is told the page size.
    resolution = long_side / (SCREEN_H / DPI)
    out = io.BytesIO()
    image.save(out, format="PDF", resolution=resolution, quality=92)
    return Document(name, "pdf", out.getvalue(), "landscape" if landscape else "portrait", 1)


def _files(doc: Document, uid: str) -> dict[str, bytes]:
    now = str(int(time.time() * 1000))
    metadata = {
        "createdTime": now,
        "lastModified": now,
        "lastOpened": "0",
        "lastOpenedPage": 0,
        "new": False,
        "parent": "",
        "pinned": False,
        "source": "",
        "type": "DocumentType",
        "visibleName": doc.name,
    }
    content = {
        "fileType": doc.kind,
        "orientation": doc.orientation,
        "coverPageNumber": 0,
        "extraMetadata": {},
        "tags": [],
        "pageTags": [],
    }
    return {
        f"{uid}.{doc.kind}": doc.body,
        f"{uid}.metadata": json.dumps(metadata, indent=4).encode(),
        f"{uid}.content": json.dumps(content, indent=4).encode(),
    }


def _tar(files: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        stamp = int(time.time())
        for path, body in files.items():
            info = tarfile.TarInfo(path)
            info.size = len(body)
            info.mode = 0o644
            info.mtime = stamp
            # Owned by root, like everything else in the store. A tar made
            # here would otherwise carry this machine's uid onto the tablet.
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            tar.addfile(info, io.BytesIO(body))
    return out.getvalue()


def push(doc: Document, host: str, timeout: int = 120) -> str:
    """Write the document into the store and restart xochitl. Returns its uuid.

    Blocks for the restart. Anything that must not stall -- a web server --
    calls this from a thread.
    """
    uid = str(uuids.uuid4())
    done = subprocess.run(
        ["ssh", *SSH_OPTIONS, host, REMOTE],
        input=_tar(_files(doc, uid)),
        capture_output=True,
        timeout=timeout,
    )
    if done.returncode != 0:
        said = done.stderr.decode(errors="replace").strip()
        raise RuntimeError(said.splitlines()[-1] if said else f"ssh exited {done.returncode}")
    return uid
