# CLAUDE.md

Rules for working on this repository. What the project *is* and how it works
lives in [README.md](README.md) and [docs/](docs/); this file is the things
that will bite you.

## Commands

```bash
./riddle --help                    # the whole surface
./riddle doctor                    # run this first, and after any change to paths
./riddle start                     # stop both halves, then start both
./riddle dev                       # both halves plus vite here, reloaded on save
./riddle diary start|stop|status|log
./riddle voice start|share|unshare
./riddle device build              # cross-compile riddled and deploy it
./riddle link                      # which routes to the tablet answer
./riddle config [--check|--write-example]
./riddle write "text"              # preview the hand to a png, --yes to draw it
./riddle testsheet --yes           # calibration ladders
```

The venv holds `numpy` and `pillow` and an editable install of
`packages/riddle`. Outside it: `zig`, `ssh`/`scp`, and for the voice half
`bun`, `tailscale` and `parakeet-cli`. The mind is an http call with an API
key, so there is no CLI for it.

There is no Python test suite. `bun run lint` (oxlint) covers the client.
`./riddle doctor` is the closest thing to an integration check and should
pass before and after anything structural.

## Invariants

- **Ink lands in whatever page is open on the tablet.** Anything that can
  leave a mark takes `--yes`, via `riddle.consent.draw(..., yes=args.yes)`.
  The `yes` argument is keyword-only and nothing reads `sys.argv`: an
  argument parser in front of the gate must not be able to defeat it. Reading
  the screen is a *separate* gate (`consent.screen`, `RIDDLE_ALLOW_SNAP`) and
  the two env switches must not be merged — they authorise different things.
  The loop is the one deliberate exception; it is ungated because starting it
  is the consent.
- **Select the pen before drawing.** An injected stroke becomes whatever tool
  xochitl has active, so with the lasso selected a page of handwriting
  silently becomes a page of selections. `riddle.apps.diary` and every
  drawing tool call `device.select("pen")` first; anything new that draws
  must too. The taps live in `taps.json` (tracked) and are re-recorded with
  `riddle taps learn pen --yes`.
- **The voice process never constructs a `Device`.** The loop owns the ssh
  pipe. Anything else that wants ink pushes an intent. Its own ssh
  connections are `web/live.py`'s screen read and `device/library.py`'s
  push into xochitl's store; neither touches the agent.
- **Never call a `Store` method from a `to_thread` worker.** One connection,
  one thread; sqlite3 enforces it. Off-thread work posts its result back.
- **No write transaction across a subprocess call, a network wait or a
  sleep.** Single statements, or `_tx()` around statements that touch nothing
  but the database.
- **An intent is never left `running`.** Unknown actions are finished as
  failed with a reason, and every failure also writes an `error` event, which
  is how the page learns outcomes without polling.
- **Three clocks, kept apart.** `Sample.t_ms` is the *tablet's* monotonic
  clock; `t_ms` in the store is milliseconds since the session row; a
  browser's `Date.now()` is neither. The host stamps events when it dequeues
  them, and the page tracks elapsed time from the server's `now_ms`.
- **A new column in `schema.sql` does nothing to an existing database.**
  `executescript` only creates what is missing. Every schema change is also a
  `MIGRATIONS` entry in `riddle/store/db.py`.
- **Tune injection against `riddle testsheet`, not by guessing.** xochitl
  smooths anything it thinks is a hand stroke, so fine detail collapses well
  above the pixel grid. Numbers in [docs/device.md](docs/device.md).
- **Skeletonised fonts fail invisibly.** Thinning can break a stem that
  rasterised too light or too small and the metrics will not show it. Look at
  the png from `riddle write` after changing font, weight or raster size.

## Where things are

| | |
|---|---|
| `packages/riddle/riddle` | all the Python, one installed package, absolute imports |
| `riddle/paths.py` | the one place that knows where the checkout and `var/` are. Never count `.parent` to find the root |
| `riddle/config.py` | every setting declared once. Never add an `os.environ.get` elsewhere |
| `riddle/cli/` | argparse groups. Module scope imports only argparse, pathlib and config; everything heavy goes inside the handler |
| `device/riddled.c` | the agent. Its header holds the *why*; the grammar is in docs/protocols.md |
| `apps/web` | the client. `src/lib/protocol.ts` mirrors docs/protocols.md by hand |
| `var/` | everything written at runtime, gitignored whole, disposable |

## Keeping the docs true

Every fact has one home. Anything else is a mirror, and a mirror changes in
the same commit.

| fact | home | mirrors |
|---|---|---|
| env vars | `riddle/config.py` | `docs/configuration.md`, `.env.example` (both generated) |
| http and websocket messages | `docs/protocols.md` | `riddle/web/server.py`, `apps/web/src/lib/protocol.ts`, `state/reducer.ts` |
| the agent's line protocol | `docs/protocols.md` | `device/riddled.c`, `riddle/device/agent.py` |
| the schema | `riddle/store/schema.sql` | `docs/store.md` |
| event kinds | `riddle/store/db.py` (`KINDS`) | `docs/store.md`, `protocol.ts`, `Timeline.tsx` |
| calibration numbers | `docs/device.md` | `Device.draw` defaults |
| what is written to disk | `docs/privacy.md` | `.gitignore` |

**If a change touches a protocol message, a setting, an event kind, a
calibration number or a file written to disk, the matching doc is part of the
diff.** If you cannot name the doc, it does not have one yet: add it.

`./riddle check` enforces the mechanical half of this — settings against the
generated files, event kinds against the client, websocket messages against
both ends.

A module docstring owns the *why* of its own module, and several are worth
reading before changing them: `web/wsock.py` on hand-rolling RFC 6455,
`voice/ears.py` on not using a VAD model, `device/screen.py` on reading a
framebuffer out of another process, `store/db.py` on the writer rules.

## Known rough edges

- `var/captures` is never pruned; `RIDDLE_AUDIO_KEEP_DAYS` only applies at
  startup, so a voice server left up for a month never prunes either.
- The `shot`, `erase` and `draw` intents are recognised and refused. The
  loop writes `shot` events of its own -- the whole-page photograph each turn
  takes while `RIDDLE_ALLOW_SNAP=1` -- so serving the intent is now mostly
  wiring a button to machinery that exists.
- There are three RDP implementations and two Zhang-Suen thinnings across
  `ink/image.py`, `ink/lineart.py` and `ink/skeleton.py`. They are *not*
  interchangeable — one is iterative on purpose because the recursive form
  blows the stack on long skeleton runs, and one is numpy-vectorised while
  the other is a pure-Python loop. Unifying them is a real behaviour change
  and belongs in its own commit.
- A dropped link is waited out, not recovered from: the loop redials until
  the tablet answers, but the half-finished stroke and its memory of its own
  ink on the page are gone. The voice server and the page reconnect on their
  own too, so nothing has to be restarted by hand.
