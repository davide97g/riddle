# Running it somewhere that is not your laptop

Since 2026-09-21 the diary runs on the homelab mini PC rather than on the Mac,
and the page it serves is on the internet at
[`riddle.davideghiotto.it`](https://riddle.davideghiotto.it). The tablet is
*not*: the loop reaches it over the LAN, the way it always did.

That split is the whole design. Ink goes over `192.168.15.x` and nothing else;
the only thing published is a page.

```
phone ──https──> Cloudflare ──tunnel──> debian:8765 ──sqlite──> the loop
                                                                   │
                                                          ssh, LAN only
                                                                   ▼
                                                            rm2-wifi :22
```

## The box

| | |
|---|---|
| Host | `debian` / `192.168.15.126`, `ssh homelab` |
| Checkout | `~/riddle`, a plain `git clone` of `main` |
| Python | `uv` made `.venv` — Debian's `python3 -m venv` needs a package that needs root, and `uv` needs neither |
| Client | built on the box: `~/.bun/bin/bun run build` in `apps/web` |
| Services | two **user** units, `riddle-voice` and `riddle-diary`, with `Linger=yes` so they survive logout and reboot |
| Tablet | `rm2-wifi` in the box's `~/.ssh/config`, its own key, appended to the tablet's `authorized_keys` beside the Mac's |

Nothing here is a container. The loop's whole job is to hold an ssh pipe open to
a device on this LAN and a sqlite file open beside the page; Docker would add a
network to cross and a key to mount and take nothing away.

```sh
systemctl --user status riddle-diary riddle-voice
journalctl --user -u riddle-diary -f
systemctl --user restart riddle-diary
```

The diary unit is `KillMode=control-group` on purpose: it owns an ssh
subprocess holding the agent's stdin, and killing only the python leaves that
ssh holding the digitizer, so the next start cannot have it. Same reasoning as
`riddle.process`, which is what runs the halves everywhere else.

### Updating it

```sh
ssh homelab 'cd ~/riddle && git pull && .venv/bin/python -m pip -q install -e packages/riddle'
ssh homelab 'cd ~/riddle/apps/web && ~/.bun/bin/bun run build'   # only if the client changed
ssh homelab 'systemctl --user restart riddle-voice riddle-diary'
```

There is no CI for this one. `riddle doctor --quick` on the box is the check
that it is still whole.

A restart is clean because both halves handle SIGTERM: they run the same
shutdown a Ctrl-C would and clear their heartbeat on the way out. A *crash* is
not, and cannot be -- the store cannot tell a dead loop from a live twin, so
`Restart=always` will bounce off "another diary answered Ns ago" until the
beat goes stale. Up to a minute, then it comes up by itself.

## The microphone

`parakeet-cli` is a whisper.cpp binary and whisper.cpp publishes none for
Linux, so the box builds its own — the one thing here that needed `sudo`, for
`build-essential` and `cmake`:

```sh
git clone --depth 1 --branch v1.9.1 https://github.com/ggml-org/whisper.cpp ~/src/whisper.cpp
cmake -B build-static -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
      -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_SERVER=OFF
cmake --build build-static -j6 --target parakeet-cli
sudo install -m755 build-static/bin/parakeet-cli /usr/local/bin/
```

`v1.9.1` because that is the version the Mac has, and **`BUILD_SHARED_LIBS=OFF`
is not a preference**: the default build links `libggml`, `libparakeet` and
friends by an rpath into the build tree, so deleting that tree breaks the
microphone and nothing says so until someone speaks. One 2.5 MB file with no
`ggml` in its `ldd` output cannot rot that way.

`/usr/local/bin` rather than `~/.local/bin` so a plain `ssh homelab` sees it —
otherwise `riddle doctor` warns the microphone is missing while the units,
which carry their own PATH, are using it perfectly well. `bun` is symlinked
there for the same reason.

CPU only, and it does not matter: 1.3s for a 1.74s clip including the model
load, which happens every run. The reMarkable's pen is slower than that.

## The gate

`RIDDLE_WEB_PASSWORD` in the box's `~/riddle/.env`. It is not decoration: the
page shows everything that was written and can ask the pen to write more, so
publishing the port without it publishes the notebook. Mechanics are in
[protocols.md](protocols.md#the-gate).

There is deliberately **no Cloudflare Access** in front of this one, unlike
`grafana` and `cinema (home)` on the same tunnel. Access is the better gate and
the cost is a second login on every device; this page is one password and a
year-long cookie.

## The tunnel

One ingress rule and one DNS record, both in Cloudflare rather than on disk —
the box's `cloudflared` runs from a dashboard-managed token.

| | |
|---|---|
| Ingress | `riddle.davideghiotto.it` -> `http://localhost:8765`, before the catch-all |
| DNS | proxied `CNAME` to the tunnel, never an `A` record |
| TLS | terminated at Cloudflare; the box serves plain HTTP on loopback |

`RIDDLE_WEB_HOST` stays `127.0.0.1`. The tunnel dials out from the box, so
nothing has to listen on the LAN and no port is forwarded.

The `Secure` flag on the login cookie comes from `X-Forwarded-Proto`, which is
cloudflared's word for it — the connection to the python process really is
plain http, and the browser's really is not.

## What is *not* on the box

- **`riddle device build`.** Cross-compiling the agent wants zig; the agent is
  already on the tablet and is built from the Mac.
- **Any CLI for the model.** The mind is one http call with the page attached,
  so there is nothing to install and nothing to log in to on a machine nobody
  sits at. That is most of why it is not the Claude Code mind any more.
- **`riddle voice share`.** That is tailscale's certificate, for when the page
  is on the Mac. Here the tunnel is the certificate.

`riddle doctor` on the box therefore reads one failure — zig — and that is the
expected state, not a thing to fix.

## Two loops, one digitizer

The heartbeat in the store is what stops a second diary starting while the
first is alive — and the store is a file on one machine. It cannot see a loop
on another. So **the Mac's halves are stopped now that the box runs them**, and
starting `riddle dev` on the Mac against the same tablet means two ssh pipes
interleaving strokes into one page with nothing to catch it.
