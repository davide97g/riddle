"""Just enough RFC 6455 to talk to one browser.

This is hand rolled rather than pulled from pypi, and the reason is the shape
of the traffic: one phone on your own tailnet sending five audio frames a
second. A dependency in a project whose entire manifest is Pillow and numpy
should buy more than that.

What keeps it honest is that the protocol above it never asks for the hard
parts. Extensions are refused, so there is no permessage-deflate to negotiate.
The control socket is always text and the audio socket is always binary and
inbound, so nothing has to guess. That leaves two things a hand roll still has
to get right, and both are handled below: a client is entitled to fragment a
message across continuation frames, and a payload may carry a 64 bit length.
"""

import asyncio
import base64
import hashlib
import struct

# The magic string every websocket handshake is hashed against. A wrong one
# still produces a well formed reply that only the browser rejects, so it is
# pinned against the worked example in RFC 6455 section 1.3:
#   accept_key("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

CONT, TEXT, BINARY, CLOSE, PING, PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA

# A frame larger than this is not something this protocol sends, so it is
# either a bug or someone poking at the port. Refuse rather than allocate.
MAX_MESSAGE = 8 << 20


def accept_key(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()


def wanted(headers: dict[str, str]) -> bool:
    return (
        headers.get("upgrade", "").lower() == "websocket"
        # Chrome sends "Upgrade"; some proxies send "keep-alive, Upgrade".
        and "upgrade" in headers.get("connection", "").lower().replace(",", " ").split()
        and bool(headers.get("sec-websocket-key"))
    )


class Closed(Exception):
    """The other end went away. Expected, not exceptional."""


class Socket:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer
        self.open = True
        # One writer, many places that might want to send: the fan-out task,
        # the pong reply, the close. Frames must not interleave.
        self._lock = asyncio.Lock()

    @classmethod
    async def upgrade(cls, reader, writer, headers: dict[str, str]) -> "Socket":
        key = headers["sec-websocket-key"]
        writer.write(
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Upgrade: websocket\r\n"
            b"Connection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: " + accept_key(key).encode() + b"\r\n\r\n"
        )
        await writer.drain()
        return cls(reader, writer)

    # --- reading ---------------------------------------------------------

    async def _frame(self) -> tuple[bool, int, bytes]:
        head = await self.reader.readexactly(2)
        fin = bool(head[0] & 0x80)
        if head[0] & 0x70:
            raise Closed("reserved bits set: an extension was negotiated")
        opcode = head[0] & 0x0F
        masked = bool(head[1] & 0x80)
        length = head[1] & 0x7F

        if length == 126:
            (length,) = struct.unpack("!H", await self.reader.readexactly(2))
        elif length == 127:
            (length,) = struct.unpack("!Q", await self.reader.readexactly(8))
        if length > MAX_MESSAGE:
            raise Closed(f"frame of {length} bytes refused")

        # Every frame from a client is masked. An unmasked one is either a
        # proxy that rewrote the stream or something that is not a browser.
        if not masked:
            raise Closed("client frame was not masked")
        mask = await self.reader.readexactly(4)
        payload = bytearray(await self.reader.readexactly(length))
        for i in range(length):
            payload[i] ^= mask[i & 3]
        return fin, opcode, bytes(payload)

    async def recv(self) -> str | bytes | None:
        """The next whole message, or None once the other end has closed."""
        chunks: list[bytes] = []
        kind = None
        while True:
            try:
                fin, opcode, payload = await self._frame()
            except (asyncio.IncompleteReadError, ConnectionResetError):
                self.open = False
                return None
            except Closed:
                await self.close(1002, "protocol error")
                return None

            if opcode == CLOSE:
                await self.close(1000, "")
                return None
            if opcode == PING:
                await self._send(PONG, payload)
                continue
            if opcode == PONG:
                continue

            if opcode in (TEXT, BINARY):
                if chunks:
                    await self.close(1002, "interleaved message")
                    return None
                kind = opcode
            elif opcode == CONT:
                if kind is None:
                    await self.close(1002, "continuation without a start")
                    return None
            else:
                await self.close(1002, f"unknown opcode {opcode}")
                return None

            chunks.append(payload)
            if sum(map(len, chunks)) > MAX_MESSAGE:
                await self.close(1009, "message too large")
                return None
            if not fin:
                continue

            body = b"".join(chunks)
            return body.decode("utf-8", "replace") if kind == TEXT else body

    def __aiter__(self):
        return self

    async def __anext__(self):
        message = await self.recv()
        if message is None:
            raise StopAsyncIteration
        return message

    # --- writing ---------------------------------------------------------

    async def _send(self, opcode: int, payload: bytes) -> None:
        if not self.open:
            return
        length = len(payload)
        if length < 126:
            head = struct.pack("!BB", 0x80 | opcode, length)
        elif length < (1 << 16):
            head = struct.pack("!BBH", 0x80 | opcode, 126, length)
        else:
            head = struct.pack("!BBQ", 0x80 | opcode, 127, length)
        try:
            async with self._lock:
                self.writer.write(head + payload)
                await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            self.open = False

    async def send(self, message: str | bytes) -> None:
        if isinstance(message, str):
            await self._send(TEXT, message.encode())
        else:
            await self._send(BINARY, message)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        if not self.open:
            return
        await self._send(CLOSE, struct.pack("!H", code) + reason.encode())
        self.open = False
        try:
            self.writer.close()
        except (ConnectionResetError, BrokenPipeError):
            pass
