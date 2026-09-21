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
instead of hanging. Nothing reconnects automatically yet.

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
