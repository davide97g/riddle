# apps/web

The page you speak into: a single-screen React app that shows the diary's
timeline, records from the microphone, and asks for a turn.

It is served by the Python half (`riddle voice`) out of `dist/`, from the
same origin as the API, so there is no CORS anywhere and no configuration to
get wrong at runtime.

```bash
riddle web install     # bun install
riddle web build       # tsc -b && vite build -> dist/
riddle web dev         # vite, proxying /api and /ws to the python server
riddle web lint        # oxlint
riddle web dev --tailnet   # hot reload behind `riddle voice share`
```

`riddle web` injects `RIDDLE_SERVER` and `RIDDLE_TAILNET` into bun's
environment; `vite.config.ts` reads them from there. `RIDDLE_SERVER` is
derived from the server's host and port by default, so changing the port
cannot silently break the dev proxy. `--tailnet` is needed behind
`tailscale serve` because tailscale terminates the TLS, so hot reload has to
dial 443 over `wss` rather than the dev port.

Without a build, the server serves a stub page saying so. The API still
works.

## What is where

| | |
|---|---|
| `src/App.tsx` | the screen: badge, timeline, composer |
| `src/state/RiddleProvider.tsx` | the one context: state, and the three things you can do |
| `src/state/reducer.ts` | all the state transitions, including the ordering rule |
| `src/hooks/useRiddleSocket.ts` | the control socket, its heartbeat and its redial |
| `src/hooks/useAudioCapture.ts` | getUserMedia, the worklet, and the audio socket |
| `public/pcm-worklet.js` | resample to 16 kHz and frame the PCM, on the audio thread |
| `src/components/Timeline.tsx` | which row component each event kind gets |
| `src/components/rows/Rows.tsx` | the row components |
| `src/lib/protocol.ts` | the wire, typed by hand |

## Three things worth knowing before changing it

**Rows sort by `t_ms`, not by id.** Transcription lags by seconds, so what
you said arrives *after* the strokes you wrote while waiting for it. Sorting
by arrival would put them in an order the room never happened in.

**The socket is the source of truth, not a cache to invalidate.**
Reconnecting is `hello { since: seq }` and the reducer's dedupe absorbs the
overlap. There is no other resync path and there does not need to be one.

**`src/lib/protocol.ts` is a hand-written mirror of
[docs/protocols.md](../../docs/protocols.md), and the two change together.**
There are a dozen messages and one backend; a codegen step would be more
moving parts than the thing it describes.

## The microphone

`getUserMedia` needs a secure context. A LAN address over plain http is not
one, and the failure is a `TypeError` long before any permission prompt — the
hook reports that case separately, pointing at `riddle voice share`, because
"mic denied" would send you looking in the wrong place.

The worklet resamples on the audio thread, where a React re-render or a
garbage collection cannot drop samples, and posts 200 ms frames as a
sequence number plus int16 PCM. A frame is **dropped rather than queued**
when the socket is backed up: a frame that arrives late is a frame in the
wrong sentence, and the server reconstructs the gap as silence from the
sequence number.

Components under `src/components/ui` are shadcn/ui, configured by
`components.json`.
