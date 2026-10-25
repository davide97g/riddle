# Which reMarkable

riddle was built on one reMarkable 2 and has only ever drawn on that one.
This page is for anyone else's: which models it can be expected to work on,
what is different about each, and what to redo before letting it write on a
page you care about. [device.md](device.md) is the tablet it was built on,
with the numbers that were measured there.

## The models

`riddle doctor` asks the tablet which model it is, from
`/sys/devices/soc0/machine`, and the answer decides the row.

| Model | It says | Status | What differs from the rM2 |
|---|---|---|---|
| reMarkable 2 | `reMarkable 2.0` | **supported**, tested on firmware 3.28 | nothing: this is the one |
| reMarkable 1 | `reMarkable 1.0`, or `reMarkable Prototype 1` on early units | **experimental**, never tested | the same Wacom digitizer and the same 1404x1872 panel, so the ink should land where it does on the rM2. Its inputs are numbered differently (pen, touch, buttons), which the agent now works out for itself. Its touchscreen is a different controller (`cyttsp5_mt`), so toolbar taps recorded on an rM2 mean nothing on it. The screen read looks for the rM2's layout of xochitl's memory and will most likely refuse; the diary works without it |
| reMarkable Paper Pro | `reMarkable Ferrari` | **unsupported**, the doctor refuses it | a different digitizer, a bigger colour panel, a 64-bit cpu and a colour framebuffer: the agent's binary, its coordinates, the screen geometry and the screen read are all wrong for it at once |
| reMarkable Paper Pro Move | `reMarkable Chiappa` | **unsupported**, the doctor refuses it | the Paper Pro's family, with a smaller panel: everything above |

Unsupported is not a judgement on the tablet. Every layer of this project
assumes one digitizer range, one screen and one cpu, and porting it is
those layers redone and measured, not a flag. Anything the doctor does not
recognise is treated the same way, because a model it has never heard of is
one nobody has checked.

## Getting ssh into a tablet

Everything here talks to the tablet over ssh, as root, and nothing else is
installed on it but the agent, one static binary in `/home/root/riddle`.

Over the cable: turn on *Settings -> Storage -> USB web interface* and the
tablet answers on `10.11.99.1`. The root password is printed under *Settings
-> Help -> Copyrights and licenses*. [device.md](device.md#getting-in) has the
details, including that a major firmware update changes both the password
and the host key.

**Give it a key, even on the cable.** riddle runs ssh with `BatchMode=yes`,
so it never answers a password prompt -- a prompt nobody is there to answer
would hang the loop mid-stroke -- and a tablet that only takes its password
looks, to `riddle link` and `riddle doctor`, like one that does not answer.

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_remarkable
ssh-copy-id -i ~/.ssh/id_ed25519_remarkable root@10.11.99.1   # asks for the password once
```

and an alias in `~/.ssh/config`, which is what everything here uses:

```
Host rm2
    HostName 10.11.99.1
    User root
    IdentityFile ~/.ssh/id_ed25519_remarkable
```

The alias is called `rm2` whatever the tablet is; `RM2_SSH_HOST` points
elsewhere if you would rather it did not.

Wifi ssh is off by default and, when turned on the vendor's way, accepts the
root password from the whole network. [device.md](device.md#how-wifi-ssh-was-turned-on)
is how it was made key-only on the rM2 this was built on, and why a firmware
update undoes it. The cable is enough to try everything here.

## Do not install Toltec or rm2fb

Not for this, and not to fix something this does. On the rM2, Toltec's
display layer is rm2fb, and rm2fb's prebuilt shim is Qt5 while xochitl is
Qt6 on current firmware, so it fails to load; that is the reason this project
reads and writes evdev and never the framebuffer
([device.md](device.md#device-state-verified-2026-09-21)). riddle needs
nothing from either, and has never been run alongside them, so a tablet with
them installed is a tablet nobody has tested this on. If you have one, check
Toltec's own list of supported firmware before you blame the diary.

## Before the first page

In order, on the cable, with a notebook you do not mind open on the tablet:

1. `./riddle device build` -- cross-compiles the agent and puts it on the
   tablet. It draws nothing.
2. `./riddle doctor` -- the model, the firmware, and a round trip through
   the agent. A `fail` on the model stops there: nothing further is checked
   on a tablet this does not support.
3. `./riddle taps learn pen --yes` -- record yourself selecting the pen.
   **The `taps.json` in this checkout is the author's tablet**, recorded in
   its touchscreen's coordinates on its firmware's toolbar. On another model,
   another touch controller or another firmware those taps press nothing, or
   something else, and with the lasso active a page of handwriting becomes a
   page of selections. Re-record them per tablet, and again after any
   firmware update moves the toolbar.
4. `./riddle testsheet --yes` -- the calibration ladders, on a blank page.
   The numbers in [device.md](device.md#injection-and-where-it-stops-working)
   were read off this sheet on an rM2 on 3.28; read your own floor off yours
   before trusting `step_ms` and `settle_ms`.
5. `./riddle snap --yes` -- only if you want the screen read (the live view,
   and the model's `look_at_page`). It reads xochitl's memory where 3.28 on
   the rM2 keeps the painted frame, so it depends on both the model and the
   firmware. A layout it does not recognise fails loudly rather than handing
   back a blank picture, and nothing else depends on it.

## How the agent finds the pen

The rM2 numbers its inputs power button, pen, touch; the rM1 numbers them
pen, touch, buttons. So the agent does not trust a number: at startup it asks
every `/dev/input/event*` what it can report. The pen is the node with
`BTN_TOOL_PEN` and absolute X, Y and pressure, the touchscreen the one with
multitouch positions and no pen. The names (`Wacom I2C Digitizer` on both,
`pt_mt` on the rM2, `cyttsp5_mt` on the rM1) only break a tie. If nothing
matches it falls back to the rM2's `event1` and `event2`, which is exactly
what it did before it asked.

On an rM2 it says nothing about this. Anywhere else it says which nodes it
took, on stderr, which the diary's log shows as `riddled: pen is ...`.

The digitizer's range is a separate question. The agent reports it as `AXIS`
lines at startup ([protocols.md](protocols.md#1-the-agent-over-ssh)), but
`riddle.ink.geometry` pins the rM2's (X 0-20966, Y 0-15725, pressure
0-4095). On an rM1, compare the two before the first page.

## What the doctor checks on the tablet

`riddle doctor --quick` skips all of this and never opens a connection.
Without it, the `tablet` group is:

| Check | ok | warn | fail |
|---|---|---|---|
| route | the ssh port answers on `RM2_SSH_HOST` | | it does not; `riddle link` finds one that does |
| model | `reMarkable 2.0` | `reMarkable 1.0` or `Prototype 1`: experimental, untested; or the tablet did not say | anything else: not supported, and the checks stop |
| firmware | always, as information: the release, and whether it is 3.28, the firmware the taps, the screen read and the injection numbers were calibrated on | | |
| agent | `PING`/`PONG` round trip through the agent | | the agent is missing or does not start: `riddle device build` |
| agent build | | the tablet's agent is not the one you last built | |

Asking the model and firmware opens no input device, so it is safe while
the diary is drawing. The agent check does start a second agent, which reads
the pen alongside the running one but draws nothing.
