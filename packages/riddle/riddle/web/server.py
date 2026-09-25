"""The page you speak into, and the socket it speaks over.

This process never touches the pen. It reads and writes the store, and the
loop -- which owns the ssh pipe -- picks up anything that wants ink by draining
the `intents` table. That is why there is no lock anywhere here and no second
`Device`: the two halves share a file, not a device.

Everything the page shows is derived by tailing the store rather than by being
told. One code path serves the live feed and the history, so a reload
reconstructs the screen from the same query that fills it in the first place.
`/ws/live` is the exception, and not from the store at all: it is the tablet's
screen, read by `riddle.web.live` over an ssh of its own.
"""

import json
import mimetypes
import time
import urllib.parse
from pathlib import Path

from riddle import config, process
from riddle.web import auth, live, wsock

POLL_S = 0.25  # how often the store is tailed for anything new
SEND_S = 5.0   # how long one page may take a frame before it is dropped
# The largest request body read at all. Only a document for the library is
# ever this big; anything past it is refused before a byte is buffered.
MAX_BODY = 65 << 20

INDEX_FALLBACK = b"""<!doctype html><meta charset=utf-8>
<title>riddle</title><body style="font:16px system-ui;padding:3rem;max-width:34rem">
<h1>riddle</h1><p>The page has not been built yet.</p>
<pre>cd web &amp;&amp; bun install &amp;&amp; bun run build</pre>
<p>The api and the socket are already up.</p>
"""


class Hub:
    """Everyone currently looking at the diary."""

    def __init__(self, store) -> None:
        self.store = store
        self.control: set[wsock.Socket] = set()
        self.seen = 0
        # What the pages have been told about the half that owns the pen, and
        # the callable that says what is true. Set by the server; `None` until
        # then, so the first tick always says it once.
        self.diary_was: bool | None = None
        self.diary_now = None

    async def say(self, message: dict) -> None:
        """One message to every open page, and no page can hold up another.

        Sent to all of them at once rather than one after another, and each
        one on a deadline. A socket whose peer has stopped reading does not
        fail -- `drain()` waits for the window to open and there is no
        timeout on it -- so a phone that went away mid-frame used to be able
        to stall the whole fan-out, and with it the only thing that delivers
        events. The page would sit there saying it was connected, and a
        reload would fix it, because replay is a different coroutine.
        """
        import asyncio

        if not self.control:
            return
        body = json.dumps(message)
        live = [sock for sock in self.control if sock.open]
        for gone in self.control - set(live):
            self.control.discard(gone)
        if not live:
            return
        done = await asyncio.gather(
            *(asyncio.wait_for(sock.send(body), SEND_S) for sock in live),
            return_exceptions=True,
        )
        for sock, outcome in zip(live, done):
            if isinstance(outcome, BaseException):
                self.control.discard(sock)
                print(f"dropped a page: {outcome!r}", flush=True)

    async def tail(self) -> None:
        """Push anything new in the store out to every open page.

        The loop and the ears write rows; nobody notifies anybody. Polling a
        local sqlite file four times a second costs less than the machinery
        that would avoid it, and it means a page that reconnects catches up
        through exactly the same path.
        """
        import asyncio

        while True:
            await asyncio.sleep(POLL_S)
            # Everything, not only the read: this coroutine is the only thing
            # that delivers events to an open page, and an exception escaping
            # it ends live updates for everybody until the server is
            # restarted -- silently, because nothing retrieves the task.
            try:
                for event in self.store.since_id(self.seen):
                    self.seen = event["id"]
                    await self.say({"type": "event", **event})
                await self.presence()
            except Exception as exc:  # the loop may be mid-write, or gone
                print(f"tail: {exc!r}", flush=True)

    async def presence(self) -> None:
        """Say when the half that owns the pen comes or goes.

        The greeting carries it, and until there was a button for it that was
        enough: a page that watched the loop die simply told you it would
        answer until you reloaded. Now the button's own outcome arrives this
        way -- starting the loop is a subprocess and a heartbeat later, not a
        reply -- so the same poll that delivers events delivers this.

        Only on a change. It is a broadcast, and the answer is the same four
        times a second.
        """
        if self.diary_now is None:
            return
        state = self.diary_now()
        if state["present"] == self.diary_was:
            return
        self.diary_was = state["present"]
        await self.say({"type": "diary", **state})


class Server:
    def __init__(self, store, root: Path, web_dir: Path, ears=None) -> None:
        self.store = store
        self.root = root
        self.web_dir = web_dir
        self.hub = Hub(store)
        self.hub.diary_now = self.diary
        self.ears = ears
        # A start or stop asked from a page, still running. One at a time:
        # two of them racing would be two ssh pipes, or a stop overtaking the
        # start it was meant to follow.
        self.working = False
        # A document on its way into the tablet's library. One at a time too:
        # each one restarts xochitl, and two restarts racing is a tablet
        # that comes back without one of them.
        self.shelving = False
        # Off unless a password is set, which is the loopback case: reaching
        # the port already means reaching the machine.
        self.gate = auth.Gate(config.get().web_password)
        # The page as it is on the tablet, for whoever opens /ws/live. It
        # dials nothing until somebody does.
        self.live = live.Live(config.get().ssh_host, config.get().live_ms)

    # --- http ------------------------------------------------------------

    async def handle(self, reader, writer) -> None:
        try:
            request = await _read_request(reader)
        except TooLarge:
            _json(writer, {"error": f"over {MAX_BODY >> 20}MB"},
                  status="413 Content Too Large")
            writer.close()
            return
        except (ConnectionResetError, ValueError):
            writer.close()
            return
        if request is None:
            writer.close()
            return
        method, target, headers, body = request
        path, _, raw_query = target.partition("?")
        query = dict(urllib.parse.parse_qsl(raw_query))

        if config.get().web_debug:
            print(f"{method} {path} ws={wsock.wanted(headers)}", flush=True)
        handed_over = False
        try:
            # `/api/health` stays open: it is what a probe asks, it says
            # nothing the login page does not, and a monitor that has to hold
            # a password is a monitor that stops working when it changes.
            if path != "/api/health" and not self.gate.allows(headers):
                self.refuse(writer, method, path, headers, body)
                return
            if path.startswith("/ws/") and wsock.wanted(headers):
                handed_over = True
                await self.socket(reader, writer, headers, path, query)
                return
            await self.route(writer, method, path, query, body)
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            if not handed_over:
                writer.close()

    def refuse(self, writer, method, path, headers, body) -> None:
        """What an unauthenticated request gets, by what asked.

        The socket is refused here rather than upgraded and closed, because a
        page that gets a live socket believes it is in. A browser asking for
        a page gets the form; anything scripted gets json it can read.
        """
        if method == "POST" and path == "/api/login":
            return self.login(writer, headers, body)
        if path.startswith("/api/") or path.startswith("/ws/"):
            return _json(writer, {"error": "locked"}, status="401 Unauthorized")
        return _send(writer, auth.page(), "text/html; charset=utf-8",
                     status="401 Unauthorized")

    def login(self, writer, headers, body) -> None:
        """One field, one cookie, and a redirect rather than a page.

        The redirect matters: it turns the POST into a GET, so a reload does
        not re-submit the password and the browser offers to remember it.
        """
        form = dict(urllib.parse.parse_qsl(body.decode("utf-8", "replace")))
        if not self.gate.admits(form.get("password", "")):
            return _send(writer, auth.page(wrong=True), "text/html; charset=utf-8",
                         status="401 Unauthorized")
        # Behind cloudflared the connection to this process is plain http and
        # the browser's is not, so the proxy's word is the only evidence that
        # a Secure cookie will ever come back.
        secure = headers.get("x-forwarded-proto", "").lower() == "https"
        return _send(writer, b"", "text/plain", status="303 See Other",
                     extra={"Location": "/", "Set-Cookie": self.gate.crumb(secure)})

    async def route(self, writer, method, path, query, body) -> None:
        if path == "/api/health":
            return _json(writer, {"ok": True, "session": self.store.session_id})

        if path == "/api/state":
            return _json(writer, self.state())

        if path == "/api/events":
            since = int(query.get("since", 0))
            limit = min(500, int(query.get("limit", 200)))
            return _json(writer, {"events": self.store.since_id(since, limit)})

        if path.startswith("/api/captures/"):
            return self.file(writer, self.root / "captures", path[len("/api/captures/"):])

        if method == "POST" and path in ("/api/send", "/api/note"):
            payload = json.loads(body or b"{}")
            if path == "/api/note":
                text = " ".join(str(payload.get("text", "")).split())
                if not text:
                    return _json(writer, {"error": "empty note"}, status="400 Bad Request")
                return _json(writer, {"id": self.store.add_event("note", text=text)})
            at_ms = int(payload.get("at_ms", self.store.now_ms()))
            intent = self.store.push_intent(
                "web", "send", {"at_ms": at_ms, "draft": payload.get("draft")}
            )
            return _json(writer, {"intent": intent, "diary": self.diary()})

        if method == "POST" and path == "/api/library":
            return await self.library(writer, query, body)

        if method == "POST" and path == "/api/understand":
            return await self.understand(writer, body)

        if path.startswith("/api/intent/"):
            found = self.store.intent(int(path.rsplit("/", 1)[1] or 0))
            if found is None:
                return _json(writer, {"error": "no such intent"}, status="404 Not Found")
            return _json(writer, found)

        if path.startswith("/api/"):
            return _json(writer, {"error": "no such route"}, status="404 Not Found")

        return self.page(writer, path)

    async def library(self, writer, query: dict, body: bytes) -> None:
        """Put the request body in the tablet's library as a document.

        This process writes to the tablet here, and still constructs no
        `Device`: the document goes into xochitl's store over an ssh of its
        own, and the pen is not involved. What it does cost is a restart of
        xochitl, which is why the page asks before it sends anything.

        Packing and pushing are both in threads -- Pillow on a big photograph
        and a restart that takes seconds -- and neither touches the store.
        """
        import asyncio

        from riddle.device import library

        if self.shelving:
            return _json(writer, {"error": "already putting something on the tablet"},
                         status="409 Conflict")
        self.shelving = True
        try:
            name = library.title(query.get("name", ""))
            doc = await asyncio.to_thread(library.pack, body, name)
            uid = await asyncio.to_thread(library.push, doc, config.get().ssh_host)
        except ValueError as exc:
            return _json(writer, {"error": str(exc)}, status="400 Bad Request")
        except Exception as exc:  # noqa: BLE001 - the tablet's answer, passed on
            print(f"library: {exc!r}", flush=True)
            return _json(writer, {"error": str(exc)}, status="502 Bad Gateway")
        finally:
            self.shelving = False
        print(f"library: {doc.name!r} ({doc.kind}, {len(doc.body) >> 10}K) -> {uid}", flush=True)
        return _json(writer, {
            "id": uid, "name": doc.name, "kind": doc.kind,
            "pages": doc.pages, "bytes": len(doc.body),
        })

    async def understand(self, writer, body: bytes) -> None:
        """What the model makes of one page: the request body, a png.

        The page sends a frame it already has -- a snapshot, current or old
        -- so nothing is read off the tablet for this, and the image is not
        kept here. It goes to OpenAI, which is the whole point, and only
        because somebody pressed the button.
        """
        import asyncio

        from riddle.mind.understand import understand

        if body[:8] != b"\x89PNG\r\n\x1a\n":
            return _json(writer, {"error": "expected a png"}, status="400 Bad Request")
        cfg = config.get()
        try:
            read = await asyncio.to_thread(
                understand, body, key=cfg.openai_key,
                model=cfg.understand_model, url=cfg.openai_url,
            )
        except Exception as exc:  # noqa: BLE001 - the model's answer, passed on
            print(f"understand: {exc}", flush=True)
            return _json(writer, {"error": str(exc)}, status="502 Bad Gateway")
        print(f"understand: {read.get('title')!r} in {read['took_ms']}ms ({read['model']})", flush=True)
        return _json(writer, read)

    def page(self, writer, path: str) -> None:
        """Serve the built app, falling back to index so routing works."""
        if not self.web_dir.is_dir():
            return _send(writer, INDEX_FALLBACK, "text/html; charset=utf-8")
        if path not in ("/", ""):
            served = self.file(writer, self.web_dir, path.lstrip("/"), quiet=True)
            if served:
                return None
        index = self.web_dir / "index.html"
        if index.is_file():
            return _send(writer, index.read_bytes(), "text/html; charset=utf-8")
        return _send(writer, INDEX_FALLBACK, "text/html; charset=utf-8")

    def file(self, writer, base: Path, rel: str, quiet: bool = False) -> bool:
        """Serve one file from under `base`, and nothing from outside it.

        A hand written static server is exactly where path traversal lives, so
        the check is on the resolved path rather than on the spelling.
        """
        target = (base / urllib.parse.unquote(rel)).resolve()
        if not target.is_relative_to(base.resolve()) or not target.is_file():
            if quiet:
                return False
            _send(writer, b"not found", "text/plain", status="404 Not Found")
            return True
        kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        cache = "public, max-age=31536000, immutable" if "/assets/" in rel or rel.startswith("assets/") else "no-cache"
        _send(writer, target.read_bytes(), kind, extra={"Cache-Control": cache})
        return True

    # --- sockets ---------------------------------------------------------

    async def socket(self, reader, writer, headers: dict, path: str, query: dict) -> None:
        sock = await wsock.Socket.upgrade(reader, writer, headers)
        if path == "/ws/events":
            await self.control(sock)
        elif path == "/ws/audio":
            await self.audio(sock, query)
        elif path == "/ws/live":
            await self.watch(sock)
        else:
            await sock.close(1003, "no such socket")

    async def control(self, sock: wsock.Socket) -> None:
        self.hub.control.add(sock)
        try:
            await sock.send(json.dumps({"type": "hello.ok", **self.state()}))
            async for raw in sock:
                if isinstance(raw, bytes):
                    continue  # the control socket is text; audio has its own
                await self.said(sock, json.loads(raw))
        except json.JSONDecodeError:
            await sock.close(1003, "not json")
        finally:
            self.hub.control.discard(sock)

    async def watch(self, sock: wsock.Socket) -> None:
        """The tablet's screen, about once a second, until the page closes.

        Behind the same switch as `riddle snap`: this reads another process's
        memory on the tablet, and a page being able to ask for it is not the
        same thing as somebody having said it may. Checked per socket rather
        than once, so the switch is what it says in `.env` now.
        """
        if not config.get().allow_snap:
            await sock.close(1008, "RIDDLE_ALLOW_SNAP is not set")
            return
        await self.live.watch(sock)

    def diary(self) -> dict:
        """Whether the half that owns the pen is running, and who runs it.

        Without the first the page promises that Send will be answered even
        when nothing is listening, and the intent simply waits. The second is
        what the page's start and stop go through, and it is worth showing:
        under systemd a stop is a request to a supervisor that may bring it
        straight back, and that is a different promise from a kill.
        """
        ago_ms = self.store.present("loop")
        return {
            "present": ago_ms is not None,
            "ago_ms": ago_ms,
            "manager": process.manager("diary"),
            "busy": self.working,
        }

    def state(self) -> dict:
        return {
            "session": self.store.session_id,
            "now_ms": self.store.now_ms(),
            "started_ms": self.store.started_ms,
            "listening": self.ears is not None,
            "live": config.get().allow_snap,
            "diary": self.diary(),
        }

    async def said(self, sock: wsock.Socket, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "ping":
            return await sock.send(json.dumps({"type": "pong", "t": msg.get("t")}))
        if kind == "hello":
            since = int(msg.get("since", 0))
            for event in self.store.since_id(since, int(msg.get("limit", 500))):
                self.hub.seen = max(self.hub.seen, event["id"])
                await sock.send(json.dumps({"type": "event", **event}))
            return
        if kind == "note":
            text = " ".join(str(msg.get("text", "")).split())
            if text:
                self.store.add_event("note", text=text)
            return
        if kind == "clear":
            # No acknowledgement: nothing is pending on it, and the page
            # learns it happened from the `tool` row the loop writes once the
            # ink is off. Like a note, this is left and not waited on.
            self.store.push_intent("web", "clear")
            return
        if kind in ("diary.start", "diary.stop"):
            return await self.half(sock, kind == "diary.start")
        if kind == "send":
            at_ms = int(msg.get("at_ms", self.store.now_ms()))
            intent = self.store.push_intent(
                "web", "send", {"at_ms": at_ms, "draft": msg.get("draft")}
            )
            # The page holds an optimistic row until the answer lands. Give it
            # the intent id so it can settle that row when the reply arrives,
            # rather than trying to match on the text it sent.
            return await sock.send(
                json.dumps({"type": "intent.ok", "id": intent, "at_ms": at_ms})
            )
        await sock.send(json.dumps({"type": "error", "message": f"unknown {kind!r}"}))

    async def half(self, sock: wsock.Socket, up: bool) -> None:
        """Start or stop the loop, from the page it serves.

        The page could already ask the loop to draw and to rub the page out.
        What it could not ask for was the loop itself, which is the one thing
        you need when it is down and you are two rooms or one tunnel away.

        This still constructs no `Device`, and that is not a technicality:
        what it starts is a child in its own process group, or a unit, and
        the ssh pipe belongs to that, never to this process. Which of the two
        is `process.manager`'s to know -- a child spawned beside a running
        unit would be the second pipe into one digitizer.

        The loop only, never this half. Stopping the voice server from the
        page it serves would take away the button that starts it again.

        The outcome does not come back here. Starting is a subprocess and
        then a heartbeat, seconds later; the page learns it the same way it
        learns everything else, from the store being tailed. Only a failure
        is answered, because nothing else will ever mention it.
        """
        import asyncio

        if self.working:
            return await sock.send(
                json.dumps({"type": "error", "message": "already starting or stopping it"})
            )
        self.working = True
        await self.hub.say({"type": "diary", **self.diary()})
        try:
            # In a thread: `begin` waits out the child's settle window and
            # `end` waits for it to die, and neither may hold up the coroutine
            # that delivers events. Nothing in there touches this store --
            # the heartbeat it clears is its own connection, opened and closed
            # in that thread.
            code, said = await asyncio.to_thread(
                process.begin if up else process.end, process.DIARY
            )
        except Exception as exc:  # noqa: BLE001 - a button may not kill the feed
            code, said = 1, repr(exc)
        finally:
            self.working = False
        print(f"page asked the diary to {'start' if up else 'stop'}: {said}", flush=True)
        if code:
            await sock.send(json.dumps({"type": "error", "message": said}))
        await self.hub.say({"type": "diary", **self.diary()})

    async def audio(self, sock: wsock.Socket, query: dict) -> None:
        """Take PCM until the page stops sending it.

        Opening this socket is what starts a recording and closing it is what
        ends one, so there is no start or stop message to fall out of step with
        what the microphone is actually doing.
        """
        if self.ears is None:
            await sock.close(1011, "this diary has no ears yet")
            return
        rate = int(query.get("rate", 16000))
        if rate != 16000:
            await sock.close(1003, f"expected 16000 Hz, got {rate}")
            return
        capture = self.ears.begin(query.get("capture", str(int(time.time()))))
        try:
            async for chunk in sock:
                if isinstance(chunk, bytes) and len(chunk) > 4:
                    # 4 byte frame index, then int16 mono pcm. The index is
                    # what places a segment where it was spoken rather than
                    # where it happened to arrive.
                    await capture.feed(
                        int.from_bytes(chunk[:4], "little"), chunk[4:]
                    )
        finally:
            await capture.done()


class TooLarge(Exception):
    """A body over `MAX_BODY`, refused on its headers alone."""


async def _read_request(reader):
    line = await reader.readline()
    if not line:
        return None
    parts = line.decode("latin-1").split()
    if len(parts) != 3:
        return None
    method, target, _ = parts

    headers: dict[str, str] = {}
    while True:
        raw = await reader.readline()
        if raw in (b"\r\n", b"\n", b""):
            break
        key, _, value = raw.decode("latin-1").partition(":")
        headers[key.strip().lower()] = value.strip()

    body = b""
    length = int(headers.get("content-length", 0) or 0)
    if length > MAX_BODY:
        raise TooLarge
    if length:
        body = await reader.readexactly(length)
    return method, target, headers, body


def _send(writer, body: bytes, kind: str, status: str = "200 OK", extra=None) -> None:
    head = [
        f"HTTP/1.1 {status}",
        f"Content-Type: {kind}",
        f"Content-Length: {len(body)}",
        "Connection: close",
    ]
    for key, value in (extra or {}).items():
        head.append(f"{key}: {value}")
    writer.write(("\r\n".join(head) + "\r\n\r\n").encode() + body)


def _json(writer, payload, status: str = "200 OK") -> None:
    _send(writer, json.dumps(payload).encode(), "application/json", status)
