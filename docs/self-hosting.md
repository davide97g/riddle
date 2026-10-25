# Your own riddle

riddle is three things you own: a **reMarkable**, a **server** at home that
talks to it, and the **app** (or the page) you open on your phone or Mac. The
app is in the App Store; the server and the tablet are this guide. Nothing
is hosted for you and there is no account: the server is yours, its data
stays on it, and the one thing that leaves it is the page you wrote, sent to
the AI model you give it a key for.

```
iPhone / Mac app ──http(s)──▶ your server ──ssh, your LAN only──▶ reMarkable 2
   or the page                (riddle voice + riddle diary)
                                    │
                                    └──https──▶ OpenAI (or any compatible API)
```

The author's own setup — a Debian mini PC, a Cloudflare tunnel, an rM2 on
wifi — is [deploy.md](deploy.md), with every reason written down. This page
is the general version of it.

## What you need

| | |
|---|---|
| **A tablet** | a reMarkable 2. A reMarkable 1 is experimental; Paper Pro and Paper Pro Move are not supported. [tablets.md](tablets.md) says why and what differs |
| **A server** | anything that stays on and is on the same network as the tablet: a mini PC, a Raspberry Pi 4/5 or other 64-bit Linux box, a NAS that runs containers, or a Mac. Linux (systemd) and macOS (launchd) are first class; Windows runs it inside WSL 2 or Docker |
| **Python 3.13+** | on the server. [`uv`](https://docs.astral.sh/uv/) will fetch one for you if the system's is older |
| **An API key** | an [OpenAI API key](https://platform.openai.com/api-keys), or a key for anything OpenAI-compatible that can see images (`RIDDLE_OPENAI_URL`). A turn costs a fraction of a cent with the default model |
| **Optional** | `bun`, to build the page for a browser (the app does not need it); `parakeet-cli` and its model, for the microphone; `zig`, to build the agent the tablet runs; `tailscale`, to reach the server from outside your home |

Before the first page: **take a backup of your tablet** (`riddle backup
create`, below). riddle never draws unless asked, but it does draw on
whatever page is open.

## Quick start

On the server:

```bash
curl -fsSL https://raw.githubusercontent.com/davide97g/riddle/main/scripts/install.sh | bash
```

That clones the repository to `~/riddle` (or wherever `RIDDLE_DIR` says),
makes the Python environment and runs `riddle setup`, which asks one question
at a time:

1. **The tablet.** Its address (USB is `10.11.99.1`; on wifi, the address
   under *Settings > Help > Copyrights and licenses*), then makes an ssh key
   for it and asks for the tablet's root password once, from that same
   screen, to install the key. It reads which model the tablet is and stops
   if it is one riddle cannot drive. If the tablet is on USB it offers to
   switch on ssh over wifi, so the server does not have to be cabled to it.
2. **The agent.** Cross-compiles `device/riddled.c` with zig and copies it
   to the tablet: a file, not ink.
3. **The model.** Your API key, into `.env` (chmod 600).
4. **The password, and Live.** The one password the app and the page sign
   in with, and whether Live (reading the tablet's screen) is on.
5. **The page.** Builds the browser client, if `bun` is there.
6. **The microphone.** Downloads the speech model (640 MB) if you want it.
7. **Reaching it.** How the phone gets to the server (below).
8. **Starting at boot.** Installs the two halves as services.

Every step can be skipped and run again on its own: `riddle setup --only
tablet`. Then:

```bash
riddle doctor               # everything, including the failures that print nothing
riddle backup create        # a snapshot of the tablet, before anything draws
```

Open a notebook on the tablet, write a question, stop, wait three seconds.

Prefer to do it by hand, or already have a clone? Every step is below.

## By hand

### The checkout

```bash
git clone https://github.com/davide97g/riddle ~/riddle && cd ~/riddle
uv venv --python 3.13 .venv && uv pip install -e packages/riddle
#   or, with a Python 3.13 already installed:
python3 -m venv .venv && .venv/bin/pip install -e packages/riddle
./riddle --help
```

`./riddle` is the only entry point; put the checkout on your `PATH` or alias
it. `cp .env.example .env` gives you every setting commented out at its
default; [configuration.md](configuration.md) is the same list, explained.

### The tablet

Everything goes over ssh as root, with a key. [tablets.md](tablets.md#getting-ssh-into-a-tablet)
has the long form; the short one:

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519_riddle
cat >> ~/.ssh/config <<'EOF'
Host rm2
    HostName 10.11.99.1
    User root
    IdentityFile ~/.ssh/id_ed25519_riddle
    IdentitiesOnly yes
EOF
ssh-copy-id -i ~/.ssh/id_ed25519_riddle.pub root@10.11.99.1   # the password from Copyrights and licenses
ssh rm2 cat /sys/devices/soc0/machine                           # reMarkable 2.0
```

and in `.env`, `RM2_SSH_HOST=rm2`.

#### ssh over wifi

`10.11.99.1` only exists on the machine the USB cable is plugged into. A
server in a cupboard needs the tablet over wifi, and the firmware keeps that
off by default. Over USB, once:

```bash
ssh rm2 'command -v rm-ssh-over-wlan && rm-ssh-over-wlan on || {
  mkdir -p /home/root/.config/remarkable &&
  touch /home/root/.config/remarkable/rm_enable_ssh_wifi_marker &&
  systemctl restart dropbear-wlan.socket; }'
ssh rm2 "ip -4 -o addr show wlan0"     # the tablet's wifi address
```

Add a second alias, `rm2-wifi`, with that address, and set
`RM2_SSH_HOST=rm2-wifi`. Then:

- **reserve that address on your router.** It is DHCP; the day it changes the
  alias points at nothing and the diary waits for a tablet that never comes.
- **a firmware update can switch it off again**, silently. If the diary
  starts waiting for the tablet after an update, this is the first thing to
  check. [device.md](device.md) has the author's key-only variant.
- the tablet sleeps, and a sleeping tablet drops wifi. The diary waits it out
  and carries on when it wakes; nothing has to be restarted.

### The agent

```bash
brew install zig            # or https://ziglang.org/download, any OS
./riddle device build       # cross-compile, copy to /home/root/riddle/riddled
```

zig is only needed where you build. A Raspberry Pi can build it too; or build
on a laptop with `--host` pointing at the tablet.

### Before the first page

The diary picks the pen in xochitl's toolbar before it writes, by tapping
where the pen tool is. Those taps are in `taps.json` and were recorded on the
author's rM2, firmware 3.28. If yours is a different firmware or model,
record your own — the command tells you what to tap:

```bash
./riddle taps learn pen --yes
./riddle testsheet --yes      # calibration ladders, on a blank page
./riddle backup create
```

### The model, and the password

```bash
# .env
RIDDLE_OPENAI_KEY=sk-...
RIDDLE_WEB_PASSWORD=something-long
# RIDDLE_ALLOW_SNAP=1        # Live, and the diary looking at the whole page
```

`chmod 600 .env`. The password is not decoration once the server is
reachable from anywhere but loopback: the page shows everything you wrote
and can ask the pen to write more.

### The microphone

Optional. Without it the app's mic button is disabled and everything else
works.

- **macOS:** `brew install whisper.cpp` (it includes `parakeet-cli`).
- **Linux:** whisper.cpp ships no binary, so build it once, statically —
  [deploy.md](deploy.md#the-microphone) has why static matters:

  ```bash
  sudo apt install build-essential cmake git libgomp1
  git clone --depth 1 --branch v1.9.1 https://github.com/ggml-org/whisper.cpp ~/src/whisper.cpp
  cd ~/src/whisper.cpp
  cmake -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
        -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_SERVER=OFF
  cmake --build build -j --target parakeet-cli
  sudo install -m755 build/bin/parakeet-cli /usr/local/bin/
  ```

Then the model, into `var/models/`:

```bash
mkdir -p var/models && curl -L -o var/models/ggml-parakeet-tdt-0.6b-v3-q8_0.bin \
  https://huggingface.co/ggml-org/parakeet-GGUF/resolve/main/ggml-parakeet-tdt-0.6b-v3-q8_0.bin
./riddle asr model
```

### The page in a browser

Optional, for opening the diary in a browser instead of the app:

```bash
curl -fsSL https://bun.sh/install | bash
./riddle web install && ./riddle web build
```

### Running it

To try it, in the foreground: `./riddle start`, and `./riddle diary log -f`.

To keep it running across reboots:

```bash
./riddle service install          # systemd user units on Linux, launch agents on a Mac
./riddle service show diary       # what it wrote, if you want to read it first
./riddle service uninstall
```

On Linux the units are `riddle-voice` and `riddle-diary`
(`systemctl --user status riddle-diary`, `journalctl --user -u riddle-diary -f`),
and `install` turns on lingering so they run without anyone logged in. If
that needs root it says so: `sudo loginctl enable-linger $USER`. On a Mac
they are `riddle.voice` and `riddle.diary` in `~/Library/LaunchAgents`,
logging to `var/log/`; they run while you are logged in.

Either way the book in the app's header is the switch for the loop, and it
goes through systemd or launchd rather than around them.

## Reaching it

The server listens on `127.0.0.1:8765` until you say otherwise. Pick one:

| | from where | how | in the app |
|---|---|---|---|
| **Tailscale** (recommended) | your own devices, anywhere | install tailscale on the server and the phone, then `riddle voice share` | the `https://<server>.<tailnet>.ts.net` url it prints |
| **Your LAN** | home wifi only | `RIDDLE_WEB_HOST=0.0.0.0` in `.env`, restart | `http://<server address>:8765` |
| **A tunnel to your domain** | anywhere, anyone with the password | e.g. a Cloudflare tunnel to `http://localhost:8765` ([deploy.md](deploy.md#the-tunnel)) | `https://riddle.example.com` |

The app takes plain `http://` on purpose, for the LAN and the tailnet. A
browser does not: it gives a page the microphone only over https, so the
page wants Tailscale or a tunnel ([voice.md](voice.md#reaching-it-from-a-phone)).

**Never** forward the port on your router or publish it without the
password: the page is your notebook.

## Connecting the app

Open riddle on the iPhone, iPad or Mac and give it the address from the
table above and `RIDDLE_WEB_PASSWORD`. The app checks both against the
server before keeping anything, keeps the address and a token made from the
password (never the password), and opens on the diary. Settings (the gear
on the phone, ⌘, on the Mac) changes server or forgets it.

[apps/apple/README.md](../apps/apple/README.md) is the app's own
documentation, including building it from source.

## In a container

For a NAS, or a server that only runs containers, or just to keep it apart:

```bash
cp deploy/docker/riddle.env.example deploy/docker/riddle.env    # fill it in
cp ~/.ssh/id_ed25519_riddle deploy/docker/ssh/
printf 'Host rm2-wifi\n  HostName 192.168.1.50\n  User root\n  IdentityFile ~/.ssh/id_ed25519_riddle\n' \
  > deploy/docker/ssh/config
docker compose -f deploy/docker/compose.yml up -d --build
```

The image holds the server, the page and the speech binary, and fetches the
speech model into its volume on first start. The agent still has to be put
on the tablet from a machine with zig (`riddle device build`).
[deploy/docker/README.md](../deploy/docker/README.md) has the rest.

## A demo server

`RIDDLE_DEMO=1` is a server with no tablet: the diary answers in the
timeline and draws nowhere, nothing dials ssh, and Live and putting a file
on a tablet are refused. It is for showing the app to somebody without
lending them your notebook — App Review signs in to one — and for trying the
app before you have a tablet at all:

```bash
docker build -f deploy/docker/Dockerfile -t riddle .      # from a clone
docker run -d -p 8765:8765 -e RIDDLE_DEMO=1 -e RIDDLE_WEB_PASSWORD=try-me \
  -e RIDDLE_OPENAI_KEY=sk-... riddle
```

It opens on a few invented pages (`riddle demo seed`, which refuses to write
into anything but a demo). Run it as its own container or checkout, never
beside a real one: it is a separate diary with its own store.

## When something is wrong

`riddle doctor` first, always; it checks the failures that print nothing.

| symptom | likely |
|---|---|
| the app says the server wants a password | `RIDDLE_WEB_PASSWORD` differs from what you typed, or was changed and the halves not restarted |
| the app cannot connect at all | the server is on loopback (see *Reaching it*); or the phone is not on the tailnet / LAN |
| the book stays closed / "waiting for the tablet" | the tablet is asleep or its wifi address changed; `riddle link` probes every route |
| ink arrives as lasso selections | the pen taps are wrong for this firmware: `riddle taps learn pen --yes` |
| nothing transcribes | `riddle asr model`, and `parakeet-cli --help` on the server |
| Live says RIDDLE_ALLOW_SNAP is not set | it is off by default; set it and restart the voice half |
| a Mac server reaches the tablet from a terminal but not as a launch agent | check System Settings > Privacy & Security > Local Network for a blocked entry, allow it, and `riddle service install` again |
| a turn fails with `openai 401` | the key in `.env` is wrong or revoked |

[privacy.md](privacy.md) is what the server keeps and how to delete it.
