# The tablet

Everything specific to this reMarkable 2: what is on it, how to reach it,
and the numbers that were measured rather than guessed.

## Device state (verified 2026-09-21)

| | |
|---|---|
| Firmware | `3.28.0.172` (`/etc/version` `20260827113527`), upgraded from `3.15.4.2` |
| OS | Codex Linux 5.8.203 (scarthgap) |
| Kernel | `5.4.70-v1.6.3-rm11x`, armv7l |
| xochitl | Qt 6.10.3 — so the Qt5 `rm2fb` shim still fails to load |
| Python on device | **none** — `/usr/bin/python*` does not exist |
| Pen node | `/dev/input/event1`, `Wacom I2C Digitizer` |
| Touch node | `/dev/input/event2` |
| Digitizer range | X 0-20966, Y 0-15725, pressure 0-4095 |
| `riddled` | runs on this firmware; `PING` -> `PONG` verified |

Two of those rows are the reason this project is shaped the way it is. No
Python on the device means the agent is C, static, musl. Qt6 xochitl against
a Qt5 shim means no framebuffer, so everything is evdev.

The 3.28 update **wiped the document store**: `/home/root/.local/share/
remarkable/xochitl` held no `.metadata` files afterwards, so a notebook
lookup resolves nothing until one is recreated. That directory also carries a
binary `.tree` sync index now, which this project ignores — it globs
`*.metadata`, which still works. `LastOpen` in `xochitl.conf` is still empty,
which is why the diary announces its target at startup and never draws
unprompted.

## Getting in

Over the cable: turn on *Settings -> Storage -> USB web interface* and the
tablet answers on `10.11.99.1`. The root password is printed under *Settings
-> Help -> Copyrights and licenses*.

Give it an alias in `~/.ssh/config` — everything here uses the alias, never a
raw address:

```
Host rm2
    HostName 10.11.99.1
    User root
    IdentityFile ~/.ssh/id_ed25519_remarkable
```

`riddle link` probes every route it can think of and times the agent's round
trip on each.

**A major firmware update regenerates both the root password and the ssh host
key.** A changed host key after an update is expected; verify the new
fingerprint on the tablet, on that same Copyrights screen, before clearing
the old one with `ssh-keygen -R 10.11.99.1`.

## Wifi instead of the cable

Point `RM2_SSH_HOST` at the tablet's wifi address. No code changes, because
every delay inside a stroke is a `SLEEP` the *agent* performs: latency shifts
a stroke in time rather than bending it, and the host only has to deliver
commands ahead of time.

Measured 2026-09-21: agent round trip is 1 ms over the cable and 5 ms median
/ 6 ms worst over wifi. The difference is far below the smallest `step_ms`
worth using, which is why the transport does not show up in the ink.

What wifi adds is a link that can drop, since the tablet sleeps and its wifi
goes with it. The agent connection sets `ServerAliveInterval` and
`ServerAliveCountMax` so a dead link surfaces in about fifteen seconds
instead of hanging, and the loop then waits for the tablet rather than
exiting with it: `riddle.device.agent.connect` redials with a backoff
capped at ten seconds, for as long as it takes, at startup and after a drop
alike. A pong is what counts as connected -- a route that does not exist
spawns ssh perfectly happily and only fails a second later.

The loop drops the half-finished stroke and forgets the shape of its own ink
when the link comes back, because the page underneath it may not be the page
it drew on. The timeline says both: a `tool` row `waiting for the tablet`,
then `back on the tablet`.

### How wifi ssh was turned on

The tablet ships it disabled behind two gates, both checked by drop-ins on
`dropbear-wlan.socket`: `/home/root/.config/remarkable/rm_enable_ssh_wifi_marker`
must exist, and `rm_disable_ssh` must not. Creating that marker is the
vendor's own toggle, and deleting it is the clean way back.

That alone would expose root over the network with the device password
accepted, so the wifi listener runs key-only instead. It could not be done
with a drop-in: `dropbear-wlan@.service` is a *symlink* to the shared
`dropbear@.service`, so systemd resolves it to the canonical name, ignores
drop-ins filed under the alias, and hands usb and wifi identical arguments.
Instead `/etc/systemd/system/riddle-sshwifi.socket` (bound to `wlan0`) and
`riddle-sshwifi@.service` are real units that add dropbear's `-s`, and the
stock `dropbear-wlan.socket` is disabled so the two do not both claim port
22. **The usb listener is untouched on purpose**: it still accepts the
password, so a lost key is recoverable over the cable.

Two things break this. A firmware update replaces `/etc`, taking both units
with it and leaving wifi ssh either off or password-accepting — re-check
after any update. And the address is DHCP (`192.168.15.135` when this was set
up, aliased as `rm2-wifi`), so it moves unless the router reserves it;
`remarkable.local` resolves but its host key is not trusted, so it is not a
drop-in fallback.

## Injection, and where it stops working

xochitl smooths anything it believes is a human stroke, so fine detail
collapses well above the pixel grid. Read the floor off a ladder rather than
guessing: `riddle testsheet --yes` draws line-gap, type-size, hatch and
radius ladders on one page.

Measured on firmware 3.28:

| | |
|---|---|
| `step_ms=6`, `settle_ms=25` | the first setting that draws a joined hand cleanly |
| `step_ms=3` | breaks letters mid-stroke |
| a line of ~67 strokes | about 10 s at that speed |

Dropped samples look like broken letters, not like lag. The levers are
`pressure`, `step_ms`, `spacing` and `settle_ms` in `Device.draw`.

Injection tuning has **not** been re-validated since the 3.28 update beyond
the above; re-run the test sheet after a firmware update before trusting any
of these numbers.

## Putting a document in the library

There is no import api on this firmware. The USB web interface has an upload
form, but only on the cable's address, and the diary lives on wifi. What
works is what xochitl does itself: the store in
`/home/root/.local/share/remarkable/xochitl` is flat, one
`<uuid>.pdf` (or `.epub`) beside a `<uuid>.metadata` and a `<uuid>.content`,
and xochitl reads it at startup. `riddle.device.library` writes those three
from a tar piped over one ssh, with fields mirroring the tablet's own files
on 3.28; xochitl fills in the rest the first time the document is opened.

**xochitl is stopped around the write**, for the reason `restore.sh` stops
it: it holds the store in memory and rewrites it on exit, so a file written
under it can be clobbered by its stale copy on the way down. The remote side
is stop, untar, sync, start, and it starts xochitl again even when the tar
fails, so a bad upload costs a restart rather than a tablet with no
interface. The restart closes whatever is open, the screen reloads for about
ten seconds, and the document waits in the library to be opened by hand.

A pdf or epub goes in untouched. An image becomes a one-page greyscale pdf:
turned by its EXIF flag, transparency flattened onto white (dropped straight
to grey, a transparent png turns black), capped at twice the screen's
resolution, and on a page whose long side is the screen's own 8.28in at
226 dpi, so 100% zoom is one pixel per pixel. A wide picture is marked
`landscape` in its `.content`, so xochitl turns the page rather than shrinking
it to a strip across a tall screen.

## Reading the screen

There is no framebuffer to read, so `riddle snap --yes` takes the cruder
route: xochitl maps `/dev/fb0` and keeps the buffer it actually paints in an
anonymous mapping directly after it, and `/proc/<pid>/mem` can be read over
ssh.

Firmware 3.24 moved that buffer from gray16 to 32-bit BGRA, so the pixel
format is pinned rather than detected. Detection is what reSnap does and it
does not work here: this tablet's `/etc/os-release` reports the Codex Linux
version, not xochitl's, so a version test picks the old format and returns
noise. The map size is the honest guard instead — a layout change fails
loudly rather than handing back a picture of nothing.

This reads another process's address space, so it has its own gate:
`--yes` or `RIDDLE_ALLOW_SNAP=1`, separate from the drawing one.

The loop answers to that same switch rather than a second one. With
`RIDDLE_ALLOW_SNAP=1` it photographs the whole page once per turn, between
the pause and the eraser, and offers it to the model as `look_at_page`; see
[loop.md](loop.md). Without it, the loop never reads the screen.

So does the page's live view, which is the same read on a loop: one ssh
connection held open by the voice server, running
`while read x; do dd ... | gzip -1 -c; done`. The host sends a newline for
each frame it wants, so it paces the tablet rather than a `sleep` over
there, and there is never more than one frame in flight. Each frame is its
own gzip member, which is the whole framing: no length prefix and no
temporary file on the tablet. Each costs the tablet about half a second of
dd and gzip, which is why `RIDDLE_LIVE_MS` defaults to a second and why the
connection is only up while a page is watching. A restarted xochitl leaves
the stream reading a dead pid; the empty frame that comes back is rejected
as a short read and the stream redials, finding the new one.
