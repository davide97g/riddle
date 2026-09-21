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
./.venv/bin/python host/tools/handwriting.py "text"  # preview the hand to /tmp/handwriting.png (add --yes to draw)
./.venv/bin/python host/tools/link.py               # probe usb/wifi routes and agent round-trip; draws nothing
```

No test suite, no linter, no package manifest. The venv holds Pillow and numpy. Dependencies outside it: `zig` (cross-compiler), `ssh`/`scp`, and the `claude` CLI on PATH.

Device access is via the ssh alias `rm2` (`~/.ssh/config` → 10.11.99.1 over USB, root) or `rm2-wifi` (→ the tablet's wifi address, key-only), both authenticating with `~/.ssh/id_ed25519_remarkable`. `host/tools/link.py` says which routes are live. `.env` holds the tablet password and tuning knobs and is gitignored; nothing in the code actually reads `RM2_PASSWORD`, it is there for manual logins. Major firmware updates regenerate both that password **and the SSH host key** — a changed host key after an update is expected, but verify the new fingerprint on the tablet (Settings → Help → Copyrights and licenses) before clearing the old one with `ssh-keygen -R 10.11.99.1`.

### Device state (verified 2026-09-21)

| | |
|---|---|
| Firmware | `3.28.0.172` (`/etc/version` `20260827113527`), upgraded from `3.15.4.2` |
| OS | Codex Linux 5.8.203 (scarthgap) |
| Kernel | `5.4.70-v1.6.3-rm11x`, armv7l |
| xochitl | Qt 6.10.3 — so the Qt5 `rm2fb` shim still fails to load |
| Python on device | **none** — `/usr/bin/python*` does not exist |
| Pen node | `/dev/input/event1`, `Wacom I2C Digitizer` (unchanged) |
| Digitizer range | X 0–20966, Y 0–15725, pressure 0–4095 — matches `geometry.py` |
| `riddled` | still runs on this firmware; `PING` → `PONG` verified |

The 3.28 update **wiped the document store**: `/home/root/.local/share/remarkable/xochitl` holds no `.metadata` files, so `notebook.find()` resolves nothing until a notebook is recreated. That directory now also carries a binary `.tree` sync index, which `notebook.py` ignores — it still globs `*.metadata`, which is fine, but the index is where 3.28 keeps its own view. `LastOpen` in `xochitl.conf` is still empty, so the "announce the target, never draw unprompted" rule stands.

Injection tuning has **not** been re-validated against xochitl 3.28; re-run `host/tools/testsheet.py --yes` before trusting the old `pressure`/`step_ms`/`spacing` values.

## Architecture

Two halves talking over one ssh pipe. Nothing listens on a port.

**`device/riddled.c`** — the on-tablet agent, spawned as `ssh rm2 /home/root/riddle/riddled`. It opens `/dev/input/event1` read-write and `select()`s on both that fd and stdin:
- pen samples out on stdout as `P <t_ms> <x> <y> <pressure>` / `U <t_ms>`
- line commands in on stdin: `DOWN x y p`, `MOVE x y p`, `UP`, `TOOL PEN|RUBBER`, `SLEEP ms`, `PING` (→ `PONG`), `QUIT`

Injection works because `write()` to an evdev node is replayed through the input core, so xochitl sees synthetic strokes as real pen input. The catch: those events also come back to *us* as reads. `echo_push`/`echo_take` keep a ring of exactly what we wrote and cancel it against the inbound stream, with a short forward scan because the input core drops unchanged ABS values. This is what lets someone keep writing while the diary is drawing.

Constraints that shaped this: the tablet ships no Python on firmware 3.28 (3.15 had one without ctypes/socket/fcntl/mmap), and rm2fb does not work (Qt6 xochitl vs. a Qt5 shim). Hence C, static musl, evdev only.

**`host/`** — Python, no package, modules import each other flat (`sys.path` hack in `host/tools/*`).

- `riddle.py` — the loop. Accumulates strokes, and when the pen has been *lifted* and idle ≥ `RIDDLE_PAUSE_MS`, fires `answer()`. Pen-down is tracked explicitly because a resting nib emits nothing (dropped duplicate coordinates), so silence alone is not a pause. `answer()` starts the model on a thread and erases the page concurrently, so the ink starts fading immediately; if the model returns nothing, the original strokes are redrawn rather than leaving a blank page.
- `device.py` — `Device` wraps the ssh subprocess, a reader thread, and an event `queue`. `sync()` is a `PING`/`PONG` round-trip, which works as a barrier only because the agent handles stdin strictly in order. `_resample()` evens out point spacing before injection.
- `geometry.py` — the Wacom↔screen mapping. The digitizer is rotated and X-inverted relative to the panel; constants were measured by tapping page corners. Everything above this layer is screen-space (1404×1872, origin top-left).
- `hershey.py` — single-stroke vector fonts from `host/fonts/*.jhf`, plus the layout engine both font kinds share. Bold is faked by re-tracing each path offset by a couple of px. `layout_runs` asks a font for a whole word if it offers `word()`, and otherwise steps glyph by glyph.
- `skeleton.py` — the other way to get a pen path: rasterise an ordinary TTF, Zhang-Suen thin it to a one-pixel ridge, then walk that ridge as a graph into ordered polylines (prune the whiskers thinning leaves, stitch runs end to end so the pen lifts less). Reports metrics in the same 32-unit em box as Hershey, so the two are interchangeable above this layer. Words are rasterised whole, because in a joined hand the exit of one letter is the entry of the next. Needs `numpy`; the per-pixel form of the thinning is too slow in plain Python.
- `style.py` — `Palette` picks the hand: >10 words gets the plain `futural`, shorter replies get the cursive accent; `*asterisks*` in the model output become emphasized accent runs. `load()` resolves a font name to whichever kind exists — a `.ttf` in `host/fonts` is skeletonised, anything else is Hershey.
- `llm.py` — shells out to `claude -p ... --output-format json --allowedTools Read`, resuming one long-lived session whose id lives in `.riddle_session`. Each turn writes a *fresh* `captures/page-<ts>-<n>.png` filename so the resumed conversation cannot answer from a stale copy of the page.
- `render.py` — strokes → cropped grayscale PNG for the model.
- `draw.py` / `diagram.py` — polyline primitives and box-and-arrow layout. No fills exist; a solid area must be hatched the way you would shade it by hand.
- `notebook.py` — resolves a notebook uuid by visible name over ssh. xochitl keeps the open document in memory and leaves `LastOpen` empty, so there is no way to know which page is actually on screen; the diary just announces its target at startup and never draws unprompted.

## Working on this

- Ink lands in **whatever page is currently open** on the tablet. Anything that draws goes through `guard.consent()` and needs `--yes` or `RIDDLE_ALLOW_DRAW=1`. Keep that gate on new tools.
- Tune injection against `testsheet.py` rather than by guessing — xochitl smooths what it thinks is a hand stroke, so fine detail collapses well above the pixel grid.
- `pressure`, `step_ms`, `spacing` and `settle_ms` in `Device.draw` are the levers for stroke fidelity vs. speed. Too fast and xochitl drops samples. Read off a ladder on firmware 3.28: `step_ms=6`, `settle_ms=25` is the first setting that draws a joined hand cleanly; `step_ms=3` breaks letters mid-stroke. A full line of ~67 strokes takes about 10s at that speed. Dropped samples look like broken letters, not like lag.
- **Select the pen before drawing.** An injected stroke becomes whatever tool xochitl has active, so with the lasso selected a page of handwriting silently becomes a page of selections — it looks like a rendering bug and is not one. `riddle.py`, `testsheet.py`, `handwriting.py` and `picture.py` all call `device.select("pen")` first; anything new that draws must too. The taps live in `taps.json` and are re-recorded with `host/tools/learn_taps.py pen`.
- Env knobs read at startup: `RM2_SSH_HOST`, `RIDDLE_NOTEBOOK`, `RIDDLE_PAUSE_MS`, `RIDDLE_INK_HEIGHT`, `RIDDLE_PRESSURE`, `RIDDLE_MODEL`, `RIDDLE_MAX_WORDS`, `RIDDLE_FONT_BODY`, `RIDDLE_FONT_ACCENT`. `RM2_WIFI_HOST` is read by `host/tools/link.py` only.
- Skeletonised fonts fail differently from Hershey ones: thinning can break a stem that rasterised too light or too small, and the metrics will not show it. Look at `handwriting.py`'s PNG after changing font, weight or `RASTER_PX`.

### Wifi instead of the cable

The link is transport-agnostic and needs no code change to move off usb: point `RM2_SSH_HOST` at the tablet's wifi address. This works because every delay inside a stroke is a `SLEEP` the *agent* executes, so latency shifts a stroke rather than distorting it — the host only has to deliver commands ahead of time. `host/tools/link.py` measures the actual `PING`/`PONG` round trip over each route.

What wifi does add is a link that can drop: the tablet sleeps and its wifi goes with it. `Device` therefore sets `ServerAliveInterval`/`ServerAliveCountMax` so a dead link surfaces in ~15s instead of hanging, and exposes `alive()`. Nothing reconnects automatically yet.

Measured 2026-09-21: agent round trip is 1 ms over the cable and 5 ms median / 6 ms worst over wifi. The difference is far below the smallest `step_ms` worth using, which is why the transport does not show up in the ink.

**How wifi ssh was turned on.** The tablet ships it disabled behind two gates, both checked by drop-ins on `dropbear-wlan.socket`: `/home/root/.config/remarkable/rm_enable_ssh_wifi_marker` must exist, and `rm_disable_ssh` must not. Creating that marker is the vendor's own toggle and deleting it is the clean way back.

That alone would expose root over the network with the device password accepted, so the wifi listener runs key-only instead. It could not be done with a drop-in: `dropbear-wlan@.service` is a *symlink* to the shared `dropbear@.service`, so systemd resolves it to the canonical name, ignores drop-ins filed under the alias, and hands usb and wifi identical arguments. Instead `/etc/systemd/system/riddle-sshwifi.socket` (bound to `wlan0`) and `riddle-sshwifi@.service` are real units that add dropbear's `-s`, and the stock `dropbear-wlan.socket` is disabled so the two do not both claim port 22. The usb listener is untouched on purpose: it still accepts the password, so a lost key is recoverable over the cable.

Two things will break this. A firmware update replaces `/etc`, taking both units with it and leaving wifi ssh either off or password-accepting — re-check after any update. And the address is DHCP (`192.168.15.135` when set up, aliased as `rm2-wifi`), so it moves unless the router reserves it; `remarkable.local` resolves but its host key is not trusted yet, so it is not a drop-in fallback.
- `host/tools/draw_test.py` calls an old `hershey.layout(origin=, max_x=)` signature and will raise; fix or delete it before relying on it.
