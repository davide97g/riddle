"""The page as it is right now, about once a second, for whoever is watching.

No model and no pen. This is the screen read from `riddle.device.screen` put
on a loop and handed to the browser: you write on the tablet and a phone
across the room shows it a second later, whether the diary is running or not.

It lives in this process rather than in the loop for two reasons. The loop
blocks for seconds at a time drawing, and a view of the page that froze
whenever an answer was being written would be a view of the wrong thing. And
a screen read is its own ssh connection that never touches the agent, so
this process can hold one without constructing a `Device` -- the pen pipe
stays the loop's alone.

Only while somebody watches. A frame is about half a second of dd and gzip
on the tablet, which is battery on a device that is otherwise asleep, so the
first viewer dials and the last one to leave hangs up.

Only frames that changed are sent. A page nobody is writing on is the same
10.5MB every second; comparing it here is a memcmp, and resending a frame
the browser already has costs a phone its data plan.
"""

import asyncio
import io
import json
import zlib

from riddle.device import screen
from riddle.device.ssh import INTERACTIVE

FRAME_S = 15.0  # a frame slower than this is a dead link, not a slow one
RETRY_S = 5.0   # between dials while the tablet does not answer
SEND_S = 5.0    # how long one page may take a frame before it is dropped
BEAT_S = 5.0    # how often the store hears that somebody is still watching
CHUNK = 1 << 16


def encode(raw: bytes, facing: str) -> bytes:
    """One read of the painted buffer as the png a browser is sent, turned
    the way the page is being read: a landscape document arrives landscape."""
    buf = io.BytesIO()
    screen.upright(screen.frame(raw), facing).save(buf, format="PNG")
    return buf.getvalue()


class Said:
    """What the tablet writes on stderr, read as it arrives.

    Every frame comes with an `O <orientation>` line, so this pipe has to be
    drained the whole time -- left alone it fills in an hour and the tablet
    blocks writing to it. Anything that is not an orientation is a complaint,
    kept for when the stream dies and somebody asks why.
    """

    def __init__(self) -> None:
        self.facing = "Portrait"
        self.complaints: list[str] = []

    async def read(self, stream) -> None:
        async for raw in stream:
            line = raw.decode(errors="replace").strip()
            if line.startswith("O "):
                name = line[2:].strip()
                self.facing = name if name in screen.UPRIGHT else "Portrait"
            elif line:
                self.complaints = (self.complaints + [line])[-5:]


class Live:
    """Everyone watching the page, and the one connection that feeds them."""

    def __init__(self, host: str, every_ms: int, on_watch=None) -> None:
        self.host = host
        self.every = every_ms / 1000
        # Told True every few seconds while anybody is watching and False
        # when the last one leaves: the loop keeps its hands off the page
        # for as long as it keeps hearing it. Called on the event loop, so it
        # may touch the store.
        self.on_watch = on_watch or (lambda on: None)
        self.viewers: set = set()
        # The newest frame, so a page that arrives mid-stream is not blank
        # until somebody next moves the pen.
        self.png: bytes | None = None
        self.state: dict = {"type": "live", "state": "dialing"}
        self.task: asyncio.Task | None = None

    async def watch(self, sock) -> None:
        """Hold one page on the feed until it goes away."""
        self.viewers.add(sock)
        try:
            await sock.send(json.dumps(self.state))
            if self.png is not None:
                await sock.send(self.png)
            if self.task is None or self.task.done():
                self.task = asyncio.create_task(self.run())
            # Nothing is expected from the page. Reading is what answers its
            # pings and notices it close.
            async for _ in sock:
                pass
        finally:
            self.viewers.discard(sock)
            if not self.viewers:
                self.hang_up()

    def hang_up(self) -> None:
        if self.task is not None:
            self.task.cancel()
            self.task = None
        self._told(False)
        # The page will have changed by the time anybody looks again.
        self.png = None
        self.state = {"type": "live", "state": "dialing"}

    async def run(self) -> None:
        """Keep a feed up for as long as anybody is watching.

        A dropped link is waited out the way the loop waits one out: the
        tablet sleeps and roams, and a view left open on a phone should find
        the page again when it wakes rather than needing a reload.
        """
        beating = asyncio.create_task(self.beats())
        try:
            await self._run()
        finally:
            beating.cancel()

    async def beats(self) -> None:
        """Watching, said out loud for as long as it is true.

        From the moment a page opens, not from the first frame: a view that
        is still dialling a sleeping tablet is somebody waiting to see the
        page, and the diary must not use those seconds to rub it out.
        """
        while self.viewers:
            self._told(True)
            await asyncio.sleep(BEAT_S)

    def _told(self, on: bool) -> None:
        try:
            self.on_watch(on)
        except Exception as exc:  # noqa: BLE001 - a missed beat must not end the feed
            print(f"live: could not say it is watched: {exc!r}", flush=True)

    async def _run(self) -> None:
        while self.viewers:
            try:
                await self.feed()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - a dead link, said out loud
                print(f"live: {exc}", flush=True)
                await self.tell("lost", str(exc))
                await asyncio.sleep(RETRY_S)

    async def feed(self) -> None:
        if self.state["state"] != "dialing":
            await self.tell("dialing")
        proc = await asyncio.create_subprocess_exec(
            "ssh", *INTERACTIVE, self.host, screen.STREAM,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        clock = asyncio.get_running_loop()
        last = None
        said = Said()
        listening = asyncio.create_task(said.read(proc.stderr))
        try:
            while self.viewers:
                began = clock.time()
                proc.stdin.write(b"\n")
                await proc.stdin.drain()
                raw = await asyncio.wait_for(self.member(proc, said, listening), FRAME_S)
                if self.state["state"] != "on":
                    await self.tell("on")
                # Turning the tablet round with nothing else changing is
                # still a new picture.
                if (raw, said.facing) != last:
                    last = (raw, said.facing)
                    # Off the event loop: a png of the whole page is tens of
                    # milliseconds, and this loop also delivers the timeline.
                    self.png = await asyncio.to_thread(encode, raw, said.facing)
                    await self.fan(self.png)
                await asyncio.sleep(max(0.0, self.every - (clock.time() - began)))
        finally:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()
            listening.cancel()

    async def member(self, proc, said: "Said", listening: asyncio.Task) -> bytes:
        """One frame: exactly one gzip member off the stream."""
        unzip = zlib.decompressobj(wbits=31)
        out = []
        while not unzip.eof:
            chunk = await proc.stdout.read(CHUNK)
            if not chunk:
                # stderr closes when the process does; wait for its last
                # words rather than racing them.
                try:
                    await asyncio.wait_for(asyncio.shield(listening), 2.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
                # The last line: ssh says why it gave up at the end, and the
                # page has one line to say it in. The log gets the rest.
                if said.complaints:
                    print(f"live: {' / '.join(said.complaints)}", flush=True)
                raise RuntimeError(said.complaints[-1] if said.complaints else "the tablet hung up")
            out.append(await asyncio.to_thread(unzip.decompress, chunk))
        return b"".join(out)

    async def tell(self, state: str, message: str | None = None) -> None:
        self.state = {"type": "live", "state": state}
        if message:
            self.state["message"] = message
        await self.fan(json.dumps(self.state))

    async def fan(self, message: str | bytes) -> None:
        """To every page at once, each on a deadline, as `Hub.say` does.

        A phone that stopped reading must not hold up the frame everybody
        else is waiting for.
        """
        live = [sock for sock in self.viewers if sock.open]
        if not live:
            return
        done = await asyncio.gather(
            *(asyncio.wait_for(sock.send(message), SEND_S) for sock in live),
            return_exceptions=True,
        )
        for sock, outcome in zip(live, done):
            if isinstance(outcome, BaseException):
                self.viewers.discard(sock)
                print(f"live: dropped a page: {outcome!r}", flush=True)
