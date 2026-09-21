# How the pieces fit

Two processes and one small C program, sharing one sqlite file.

```
  the tablet                    your machine
 ┌────────────┐
 │  xochitl   │            ┌──────────────────────────┐
 │            │            │  riddle diary            │   owns the ssh pipe;
 │ /dev/input │◄───ssh────►│  (riddle.apps.diary)     │   the only thing that
 │  event1/2  │            └───────────┬──────────────┘   moves the pen
 │  riddled   │                        │
 └────────────┘                        │ writes strokes, turns, replies
                                       │ drains intents
                            ┌──────────▼──────────┐
                            │  var/riddle.db      │  one clock, two writers
                            └──────────▲──────────┘
                                       │ writes speech, notes
                                       │ leaves intents
 ┌────────────┐            ┌───────────┴──────────────┐
 │  a phone   │◄──https───►│  riddle voice            │   never opens ssh,
 │  (browser) │  tailscale │  (riddle.apps.voice)     │   never draws
 └────────────┘            └──────────────────────────┘
```

The two halves **share a file, not a device**. That is the whole design: the
loop owns the ssh pipe and blocks for seconds at a time drawing, so a web
server cannot live inside it, and anything that wants ink leaves a note in
`intents` for the loop to pick up.

## Who writes what

| table | the loop | the voice server |
|---|---|---|
| `sessions` | creates or joins, beats `loop_ms` | creates or joins, beats `voice_ms` |
| `events` | `strokes`, `reply`, `tool`, `error`, kept `note`s | `speech`, typed `note`s |
| `strokes` | one row per stroke of a turn | — |
| `turns` | the whole row | — |
| `intents` | claims and finishes | pushes |
| `state` | reads `asr.inflight` | writes it |

Whoever starts first writes the session row; the other joins it. What matters
is that every `t_ms` has one origin, not which process owns it — and the page
is meant to be usable before the tablet is plugged in.

Details: [docs/store.md](store.md).

## The packages

Everything Python is one installable package, `packages/riddle/riddle`.

| package | what lives there |
|---|---|
| `riddle.device` | the ssh transport. `agent` (the pipe to `riddled`, and the only thing that injects), `ssh` (options and remote paths), `taps` (recorded toolbar presses), `screen` (the framebuffer out of xochitl's memory), `notebook`, `pages` (noticing a page turn) |
| `riddle.ink` | marks on a page. `geometry` (the only module that knows the digitizer is rotated), `hershey` and `skeleton` (the two ways to turn text into pen paths, interchangeable above `style`), `style`, `render`, `draw`, `diagram`, `page`, `image`, `lineart` |
| `riddle.mind` | who answers. `persona` (the words, shared), `deepseek` (the default: one http call, fast and cheap, blind), `eyes` (a vision model reading the page for it), `llm` (the claude subprocess, which can see and search), `memory` (the lines that survive a reset) |
| `riddle.store` | `db` and `schema.sql` |
| `riddle.voice` | `ears`: the energy gate and the speech model |
| `riddle.web` | `server` (http and websockets) and `wsock` (enough RFC 6455 for one browser) |
| `riddle.apps` | `diary` and `voice`, the two processes |
| `riddle.tools` | the operator commands the CLI dispatches to |
| top level | `paths`, `config`, `consent`, `process` (both halves in the background), `dev` (both halves plus the client's dev server, here, reloaded on save), `toolchain` (how `bun` is invoked), `tailnet`, `probe`, `doctor`, `cli` |

Outside the package: `device/riddled.c` (the agent), `apps/web` (the client),
`scripts/backup` (tar over ssh, which shell does better), `var` (everything
written at runtime, gitignored whole).

## The two hands

Text becomes pen paths two ways, and they are interchangeable above
`riddle.ink.style`:

- **Hershey** `.jhf` fonts are single-stroke vector fonts from the 1960s,
  where the letter *is* the path a nib follows.
- **Skeletonised** TTFs are rasterised, thinned to a one-pixel ridge with
  Zhang-Suen, and walked as a graph into ordered polylines. Words are
  rasterised whole, because in a joined hand the exit of one letter is the
  entry of the next.

An outline font used directly would be traced as hollow, double-walled
letters: a pen cannot fill. Skeletonising is what lets the diary write in a
joined hand rather than in wire letters.

Skeletons fail differently from Hershey: thinning can break a stem that
rasterised too light or too small, and the metrics will not show it. Look at
the png from `riddle write` after changing font, weight or raster size.

## Where to read next

- [loop.md](loop.md) — what counts as a question, and what a turn does
- [voice.md](voice.md) — the page you speak into, from nothing
- [store.md](store.md) — the clock, the tables, the intent contract
- [protocols.md](protocols.md) — both wires, in full
- [device.md](device.md) — the tablet itself: firmware, ssh, calibration
- [configuration.md](configuration.md) — every setting
- [privacy.md](privacy.md) — what is written down, and what leaves the machine
