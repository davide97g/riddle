# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A "Tom Riddle diary" for a reMarkable 2 tablet. You handwrite on a page, pause, your ink is erased, and the diary writes an answer back in its own hand. There is no framebuffer access and no app: everything is done by reading and injecting raw evdev pen events on the device.

## Commands

```bash
./device/build.sh              # cross-compile riddled (zig cc, arm-linux-musleabihf, static) + scp to rm2
./run.sh                       # start the diary loop (sources .env, uses ./.venv/bin/python)

# Tools (each refuses to draw without --yes; see host/tools/guard.py)
./.venv/bin/python host/tools/clear_page.py --yes   # eraser-sweep the visible page
./.venv/bin/python host/tools/scene.py --yes        # flowchart + snake, exercises draw.py/diagram.py
./.venv/bin/python host/tools/testsheet.py --yes    # calibration ladders: line gap, type size, hatch, radius
```

No test suite, no linter, no package manifest. The venv holds only Pillow. Dependencies outside it: `zig` (cross-compiler), `ssh`/`scp`, and the `claude` CLI on PATH.

Device access is via the ssh alias `rm2` (`~/.ssh/config` → 10.11.99.1 over USB, root). `.env` holds the tablet password and tuning knobs and is gitignored; the reMarkable regenerates the password on major firmware updates.

## Architecture

Two halves talking over one ssh pipe. Nothing listens on a port.

**`device/riddled.c`** — the on-tablet agent, spawned as `ssh rm2 /home/root/riddle/riddled`. It opens `/dev/input/event1` read-write and `select()`s on both that fd and stdin:
- pen samples out on stdout as `P <t_ms> <x> <y> <pressure>` / `U <t_ms>`
- line commands in on stdin: `DOWN x y p`, `MOVE x y p`, `UP`, `TOOL PEN|RUBBER`, `SLEEP ms`, `PING` (→ `PONG`), `QUIT`

Injection works because `write()` to an evdev node is replayed through the input core, so xochitl sees synthetic strokes as real pen input. The catch: those events also come back to *us* as reads. `echo_push`/`echo_take` keep a ring of exactly what we wrote and cancel it against the inbound stream, with a short forward scan because the input core drops unchanged ABS values. This is what lets someone keep writing while the diary is drawing.

Constraints that shaped this: the tablet's Python has no ctypes/socket/fcntl/mmap, and rm2fb does not work on firmware 3.15 (Qt6 xochitl vs. a Qt5 shim). Hence C, static musl, evdev only.

**`host/`** — Python, no package, modules import each other flat (`sys.path` hack in `host/tools/*`).

- `riddle.py` — the loop. Accumulates strokes, and when the pen has been *lifted* and idle ≥ `RIDDLE_PAUSE_MS`, fires `answer()`. Pen-down is tracked explicitly because a resting nib emits nothing (dropped duplicate coordinates), so silence alone is not a pause. `answer()` starts the model on a thread and erases the page concurrently, so the ink starts fading immediately; if the model returns nothing, the original strokes are redrawn rather than leaving a blank page.
- `device.py` — `Device` wraps the ssh subprocess, a reader thread, and an event `queue`. `sync()` is a `PING`/`PONG` round-trip, which works as a barrier only because the agent handles stdin strictly in order. `_resample()` evens out point spacing before injection.
- `geometry.py` — the Wacom↔screen mapping. The digitizer is rotated and X-inverted relative to the panel; constants were measured by tapping page corners. Everything above this layer is screen-space (1404×1872, origin top-left).
- `hershey.py` — single-stroke vector fonts from `host/fonts/*.jhf`. Outline fonts are useless here: a pen can only trace them as hollow letters, so the Hershey centreline data *is* the nib path. Bold is faked by re-tracing each path offset by a couple of px.
- `style.py` — `Palette` picks the hand: >10 words gets the plain `futural`, shorter replies get cursive `scripts`; `*asterisks*` in the model output become emphasized accent runs.
- `llm.py` — shells out to `claude -p ... --output-format json --allowedTools Read`, resuming one long-lived session whose id lives in `.riddle_session`. Each turn writes a *fresh* `captures/page-<ts>-<n>.png` filename so the resumed conversation cannot answer from a stale copy of the page.
- `render.py` — strokes → cropped grayscale PNG for the model.
- `draw.py` / `diagram.py` — polyline primitives and box-and-arrow layout. No fills exist; a solid area must be hatched the way you would shade it by hand.
- `notebook.py` — resolves a notebook uuid by visible name over ssh. xochitl keeps the open document in memory and leaves `LastOpen` empty, so there is no way to know which page is actually on screen; the diary just announces its target at startup and never draws unprompted.

## Working on this

- Ink lands in **whatever page is currently open** on the tablet. Anything that draws goes through `guard.consent()` and needs `--yes` or `RIDDLE_ALLOW_DRAW=1`. Keep that gate on new tools.
- Tune injection against `testsheet.py` rather than by guessing — xochitl smooths what it thinks is a hand stroke, so fine detail collapses well above the pixel grid.
- `pressure`, `step_ms`, `spacing` and `settle_ms` in `Device.draw` are the levers for stroke fidelity vs. speed. Too fast and xochitl drops samples.
- Env knobs read at startup: `RM2_SSH_HOST`, `RIDDLE_NOTEBOOK`, `RIDDLE_PAUSE_MS`, `RIDDLE_INK_HEIGHT`, `RIDDLE_PRESSURE`, `RIDDLE_MODEL`, `RIDDLE_MAX_WORDS`, `RIDDLE_FONT_BODY`, `RIDDLE_FONT_ACCENT`.
- `host/tools/draw_test.py` calls an old `hershey.layout(origin=, max_x=)` signature and will raise; fix or delete it before relying on it.
