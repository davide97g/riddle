# riddle

A Tom Riddle diary for the reMarkable 2.

You write a question on the page by hand. You pause. Your ink fades away, and
the diary writes an answer back underneath it, in its own handwriting, one
stroke at a time.

There is no app on the tablet and no framebuffer access. The whole thing is
done by reading and injecting raw pen events, so as far as the reMarkable's
own software is concerned, something invisible is holding a second stylus.

There is also a second half: a page you can open on your phone, speak into,
and ask the diary for an answer from. It never touches the tablet — it leaves
a note in a small shared database and the first half picks it up.

## Two halves

```
riddle diary   owns the ssh pipe to the tablet. Watches the page, decides
               what is a question, asks the model, draws the answer.

riddle voice   a page you speak into, served on loopback. Records,
               transcribes, shows a timeline, and asks the diary for a turn.
```

They share one sqlite file and no device. Either can run alone.

## Quickstart

You need `zig` (the cross-compiler), `ssh`/`scp`, the `claude` CLI, and
Python 3.13+. For the voice half you also need `bun`, `tailscale`, and
`parakeet-cli` with its model.

```bash
# 1. an ssh alias for the tablet (Settings > Storage > USB web interface)
cat >> ~/.ssh/config <<'EOF'
Host rm2
    HostName 10.11.99.1
    User root
EOF

# 2. the venv and the package
python3 -m venv .venv
./.venv/bin/pip install -e packages/riddle

# 3. your settings
cp .env.example .env     # every line is commented out at its default

# 4. the agent, cross-compiled and deployed
./riddle device build

# 5. check everything before trusting it
./riddle doctor

# 6. open a notebook on the tablet, then
./riddle diary start
```

Write something. Stop. Wait three seconds.

For the page you speak into — [docs/voice.md](docs/voice.md) has the whole
setup, including why it will not get a microphone over plain http:

```bash
./riddle web install && ./riddle web build
./riddle voice start
./riddle voice share      # a real certificate, for a phone
```

## The commands

`./riddle` is the only entry point. `./riddle --help` lists them all; the
ones worth knowing:

```bash
./riddle diary start|stop|status|log|restart   # the loop, in the background
./riddle diary start --foreground              # or in this terminal
./riddle voice start|...|share|unshare         # the page you speak into
./riddle device build                          # cross-compile and deploy the agent
./riddle link                                  # which routes to the tablet work
./riddle doctor                                # check everything, including
                                               #   the failures that print nothing
./riddle config                                # every setting, and where it came from
./riddle write "some words"                    # preview the diary's hand to a png
./riddle testsheet --yes                       # calibration ladders
./riddle clear --yes                           # eraser-sweep the page
./riddle snap --yes                            # photograph the tablet's screen
./riddle backup create|verify|restore          # snapshots of the tablet
```

## A warning about where the ink goes

**The diary draws on whatever page is currently open on your tablet.** It has
no way to know which one that is — xochitl holds the open document in memory
and leaves `LastOpen` empty on disk — so it announces the page it *intends*
to use at startup and otherwise never draws unprompted.

Every command that can leave a mark asks first: it needs `--yes`, or a
standing `RIDDLE_ALLOW_DRAW=1`. The loop is the deliberate exception, because
starting it *is* the consent; it says which notebook it means when it starts.
Reading the tablet's screen is a separate gate, `RIDDLE_ALLOW_SNAP`, because
it reads another process's memory rather than writing to a page.

Take a backup first: `./riddle backup create`.

## It records things

Photographs of your handwriting, recordings of the room, transcripts, and
what each turn cost — all under `var/`, which is gitignored whole. The page
and the transcript window go to Anthropic on every turn, and the model is
allowed to search the web.

Anything said near the microphone inside a turn's window becomes part of the
question, including other people in the room.

[docs/privacy.md](docs/privacy.md) has the full list and how to delete it.

## Where things are

```
riddle                 the one command
packages/riddle/       all the Python, as one installed package
  riddle/device/         the ssh transport, and the tablet
  riddle/ink/            geometry, fonts, strokes, pictures
  riddle/mind/           the model, and what it remembers
  riddle/store/          the sqlite file both halves share
  riddle/voice/          the energy gate and the speech model
  riddle/web/            http and websockets, hand rolled
  riddle/apps/           the two processes
device/riddled.c       the on-tablet agent: evdev in, evdev out
apps/web/              the page you speak into, as a front end
scripts/backup/        snapshot and restore, in shell
docs/                  how it works, and why
var/                   everything written at runtime. gitignored, disposable
```

## How it actually works

- [docs/architecture.md](docs/architecture.md) — the map, and who writes what
- [docs/loop.md](docs/loop.md) — what counts as a question, and what a turn does
- [docs/voice.md](docs/voice.md) — the speaking half, from nothing
- [docs/store.md](docs/store.md) — the shared clock and the intent contract
- [docs/protocols.md](docs/protocols.md) — both wires, in full
- [docs/device.md](docs/device.md) — firmware, ssh over wifi, injection limits
- [docs/configuration.md](docs/configuration.md) — every setting
- [docs/privacy.md](docs/privacy.md) — what is written down
- [docs/backup.md](docs/backup.md) — snapshots of the tablet

A few decisions that look odd until you know why:

- **C, not Python, on the device.** Firmware 3.28 ships no Python at all;
  3.15 shipped one built without ctypes, socket, fcntl or mmap. Either way it
  cannot touch an input device.
- **Skeletons, not outlines.** A pen cannot fill, so an ordinary font would
  be traced as hollow, double-walled letters. Rasterising a word and thinning
  it to a one-pixel ridge turns any font into the line a nib would have
  taken.
- **evdev, not the framebuffer.** `rm2fb` does not work: xochitl is Qt6 and
  the prebuilt shim is still Qt5.
- **Wifi works as well as the cable**, because every pause inside a stroke is
  performed by the agent on the tablet. Latency moves a stroke in time; it
  does not bend it. 1 ms on usb, 5 ms on wifi.
- **The pause is measured from a pen lift, not from silence.** A nib resting
  on the page emits nothing, because the input core drops repeated
  coordinates.
- **Erasing and thinking happen at the same time**, so your ink starts fading
  the moment you stop writing. It also buys, for free, the moment the speech
  model needs to finish the sentence you just said.
- **A hand-rolled websocket.** One phone on your own tailnet sending five
  audio frames a second. A dependency in a project whose entire manifest is
  numpy and pillow should buy more than that.

## License

MIT. See [LICENSE](LICENSE).
