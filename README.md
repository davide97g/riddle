# riddle

A Tom Riddle diary for the reMarkable 2.

You write a question on the page by hand. You pause. Your ink fades away, and
the diary writes an answer back underneath it, in its own handwriting, one
stroke at a time.

There is no app on the tablet and no framebuffer access. The whole thing is
done by reading and injecting raw pen events, so as far as the reMarkable's own
software is concerned, something invisible is holding a second stylus.

## How it works

Two halves talking over a single ssh pipe. Nothing listens on a port.

**On the tablet** sits `riddled`, a small C program that opens the digitizer at
`/dev/input/event1` for reading *and* writing. It streams your pen samples out
on stdout and takes drawing commands on stdin:

```
P <t_ms> <x> <y> <pressure>     a pen sample, going out
U <t_ms>                        pen lifted
DOWN x y p / MOVE x y p / UP    a stroke, coming in
TOOL PEN | RUBBER               pen or eraser
```

Injection works because writing to an evdev node replays the events through the
kernel's input core, so xochitl cannot tell a synthetic stroke from a real one.
The awkward part is that those events also come straight back to us as reads.
`riddled` keeps a ring of exactly what it wrote and cancels it against the
inbound stream, which is what lets you keep writing while the diary is still
drawing its reply.

**On the host** is the Python half. It accumulates your strokes, waits for the
pen to be lifted and stay idle, then renders the page to a PNG and asks Claude
what the diary should say. The reply is drawn back with Hershey fonts —
single-stroke vector fonts from the 1960s, where the letter *is* the path the
nib follows. Outline fonts are useless here, because a pen tracing one would
just draw hollow letters.

A few decisions that look odd until you know why:

- **C, not Python, on the device.** Firmware 3.28 ships no Python at all; 3.15
  shipped one built without ctypes, socket, fcntl or mmap. Either way it cannot
  touch an input device.
- **evdev, not the framebuffer.** `rm2fb` does not work: xochitl is Qt6
  (6.10.3 on firmware 3.28) and the prebuilt shim is still Qt5.
- **The pause is measured from a pen lift, not from silence.** A nib resting on
  the page emits nothing, because the input core drops repeated coordinates.
- **Erasing and thinking happen at the same time**, so your ink starts fading
  the moment you stop writing rather than after the model replies. If the model
  returns nothing, your original strokes are drawn back.

## Setup

You will need `zig` (as the cross-compiler), `ssh`/`scp`, the `claude` CLI, and
a Python with Pillow.

1. Enable *Settings → Storage → USB web interface* on the tablet and plug it in
   over USB. That is what brings up `10.11.99.1`.
2. Add an ssh alias for it in `~/.ssh/config`:

   ```
   Host rm2
       HostName 10.11.99.1
       User root
   ```

   The root password is printed on the tablet under *Settings → Help →
   Copyrights and licenses*. Copying a key over with `ssh-copy-id` saves typing
   it every time. Note that major firmware updates regenerate it, along with
   the device's SSH host key — after an update `ssh` will refuse to connect
   until you check the new fingerprint on that same screen and then run
   `ssh-keygen -R 10.11.99.1`.
3. `cp .env.example .env` and fill it in.
4. `python3 -m venv .venv && ./.venv/bin/pip install pillow`
5. `./device/build.sh` — cross-compiles the agent and drops it on the tablet.
6. `./run.sh` — open a notebook on the tablet, write something, and stop.

## Tools

Handy for calibration. Each one refuses to draw unless you pass `--yes`.

```bash
./.venv/bin/python host/tools/testsheet.py --yes    # line gap, type size, hatch, radius ladders
./.venv/bin/python host/tools/scene.py --yes        # a flowchart and a snake
./.venv/bin/python host/tools/clear_page.py --yes   # eraser-sweep the visible page
```

Tune stroke fidelity against `testsheet.py` rather than by guessing. xochitl
smooths anything it believes is a human stroke, so fine detail collapses well
above the pixel grid. The levers are `pressure`, `step_ms`, `spacing` and
`settle_ms` in `Device.draw`. Push it too fast and samples get dropped.

## A warning about where the ink goes

**The diary draws on whatever page is currently open on your tablet.** It has no
way to know which one that is — xochitl holds the open document in memory and
leaves `LastOpen` empty on disk — so it announces the page it *intends* to use
at startup and otherwise never draws unprompted.

Anything that draws goes through `guard.consent()` and needs `--yes` or
`RIDDLE_ALLOW_DRAW=1`. Keep that gate on anything new you write. And take a
backup first.

## Backups

`backup/` has a read-only snapshot tool for the tablet: it copies the document
store and system config to your machine and never writes to the device. The
restore side is dry-run by default and never deletes. See
[backup/README.md](backup/README.md).

Snapshots contain the tablet's ssh host keys, shell history and every notebook
you own, so they are gitignored. Keep them off shared drives.

## Layout

```
device/riddled.c     the on-tablet agent: evdev in, evdev out
host/riddle.py       the loop — accumulate strokes, detect the pause, answer
host/device.py       ssh subprocess, reader thread, event queue
host/geometry.py     digitizer to screen mapping (it is rotated and X-inverted)
host/hershey.py      single-stroke vector fonts
host/style.py        picks the hand: cursive for short replies, plainer for long
host/llm.py          shells out to the claude CLI, resuming one long session
host/draw.py         polyline primitives; there are no fills, only hatching
backup/              snapshot and restore tooling for the tablet
```

## License

MIT. See [LICENSE](LICENSE).
