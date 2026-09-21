# The two wires

Both protocols are documented **here and nowhere else**. The README used to
carry a copy of the first one and it had already drifted: it listed six
commands out of nine and none of the lines the agent had learned to send.

## 1. The agent, over ssh

`riddled` is spawned as `ssh <host> /home/root/riddle/riddled` and speaks
plain lines over that pipe's stdout and stdin. It `select()`s on the pen
node and on stdin together, so it can be drawing and reporting at once.

### Out, on stdout

| Line | Meaning |
|---|---|
| `READY` | the input devices are open |
| `AXIS <name> <min> <max>` | one digitizer axis, sent once at startup |
| `P <t_ms> <x> <y> <pressure>` | a pen sample |
| `U <t_ms>` | the nib left the page |
| `K PEN` / `K RUBBER` | which end of the pen is over the page |
| `T <x> <y>` | a finger, from the touch node |
| `PONG` | the answer to `PING` |

`t_ms` is **the tablet's own monotonic clock**. It is not the store's clock
and not the host's; nothing may compare the two. The host stamps events with
its own clock when it takes them off the queue, and the 1-5 ms of transport
is far below anything that matters.

Coordinates are raw Wacom units (X 0-20966, Y 0-15725, pressure 0-4095), and
the digitizer is rotated and X-inverted relative to the panel. `riddle.ink.geometry`
is the only place that knows this; everything above it is screen space,
1404x1872, origin top left.

### In, on stdin

| Command | Meaning |
|---|---|
| `DOWN x y p` | put the nib down at a point |
| `MOVE x y p` | drag it |
| `UP` | lift it |
| `TOOL PEN` / `TOOL RUBBER` | present the nib or the eraser end |
| `SLEEP ms` | wait, on the tablet |
| `TAP x y [ms]` | a touch press, for pressing toolbar buttons |
| `PING` | replies `PONG` |
| `QUIT` | exit |

**Every delay inside a stroke is a `SLEEP` the agent performs**, which is why
the link's latency shifts a stroke in time rather than bending it, and why
wifi draws exactly as well as the cable.

`PING`/`PONG` is a barrier only because stdin is handled strictly in order:
when the `PONG` comes back, everything sent before it has been injected.

### Why injection works, and what it costs

Writing to an evdev node replays the events through the kernel's input core,
so xochitl cannot tell a synthetic stroke from a real one. The catch is that
those events come back to the agent as reads. `echo_push`/`echo_take` keep a
ring of exactly what was written and cancel it against the inbound stream,
with a short forward scan because the input core drops unchanged ABS values.
That cancellation is what lets someone keep writing while the diary draws.

## 2. The page you speak into, over http and websockets

One asyncio server on `127.0.0.1:8765`. HTTP and both sockets share the port;
a request to `/ws/*` with the websocket headers is upgraded, everything else
is routed.

### HTTP

| Route | Returns |
|---|---|
| `GET /api/health` | `{ok, session}` |
| `GET /api/state` | `{session, started_ms, now_ms, listening, diary:{present, ago_ms}}` |
| `GET /api/events?since=&limit=` | `{events:[DiaryEvent]}`, limit capped at 500 |
| `GET /api/captures/<name>` | a png from `var/captures`, path-traversal checked on the resolved path |
| `GET /api/intent/<id>` | `{id, state, result}` |
| `POST /api/note` | `{id}` — records a typed note |
| `POST /api/send` | `{intent, diary}` — asks the diary for a turn |
| `POST /api/login` | form-encoded `password`; `303` to `/` with the cookie, or the form again with `401` |
| anything else | the built client, with index as the fallback so routing works |

There is deliberately **no route for `var/audio`**. Those files are a
recording of a room.

### The gate

With `RIDDLE_WEB_PASSWORD` unset there is none, which is the loopback case.
Set it and every route above except `GET /api/health` needs the cookie
`riddle=hmac(password, "riddle-v1")`: a browser gets the login page with a
`401`, anything under `/api/` gets `{"error":"locked"}`, and `/ws/*` is
refused *before* the upgrade — a page handed a live socket believes it is in.

A cookie rather than HTTP Basic because the browser's WebSocket API cannot
send an `Authorization` header, and `/ws/events` is the whole feed and the
send path both. The token is one-way and deterministic: a restart logs nobody
out, nothing is stored on disk, and changing the password is what revokes it.

### `/ws/events` — text, both ways

Client to server:

| Message | Effect |
|---|---|
| `hello {since, limit?}` | replays everything newer than `since` |
| `ping {t}` | answered with `pong {t}` |
| `note {text}` | records a typed note |
| `send {at_ms, draft}` | leaves a `send` intent, answered with `intent.ok` |
| `clear {}` | leaves a `clear` intent: the diary rubs its ink off the page, forgets the conversation and deletes this session. Not acknowledged; the `tool` row with `meta.doing` `cleared` is what says it happened |

Server to client:

| Message | Meaning |
|---|---|
| `hello.ok {session, started_ms, now_ms, listening, diary}` | the greeting |
| `event {...DiaryEvent}` | one row of the timeline |
| `pong {t}` | |
| `hearing {on}` | the energy gate opened or closed |
| `pending {clip, on}` | a clip is with the speech model |
| `intent.ok {id, at_ms}` | a send was recorded, and this is its id |
| `error {message}` | |

Reconnecting is `hello {since: seq}` and nothing else. There is no other
resync path and there does not need to be one.

### `/ws/audio?rate=16000&capture=<name>` — binary, inbound only

Each frame is **4 bytes of little-endian sequence number, then 3200 signed
16-bit little-endian mono samples at 16 kHz** — 200 ms, 6404 bytes.

**Opening the socket starts a recording and closing it ends one.** There is
no start or stop message, so nothing can fall out of step with what the
microphone is actually doing. A dropped frame is reconstructed as real
silence from the sequence number, up to five seconds, because a gap is
something that happened in the room rather than something to paper over.

The server rejects any rate but 16000 at the handshake.

## When you change any of this

A change here is a change in four places at once:

- the agent's line protocol: `device/riddled.c`, `riddle.device.agent`, this file
- the http and websocket messages: `riddle.web.server`,
  `apps/web/src/lib/protocol.ts`, `apps/web/src/state/reducer.ts`, this file

`apps/web/src/lib/protocol.ts` is a hand-written mirror of this document.
There are a dozen messages and one backend; a codegen step would be more
moving parts than the thing it describes.
