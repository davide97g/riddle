# deploy/docker

riddle's server as one container: the page, the loop, and the speech binary.
The checkout's own way of running (`riddle service install`) is still the
first choice on a Linux box or a Mac, for the reasons in
[docs/deploy.md](../../docs/deploy.md); this is for a server that only runs
containers, and for the demo server.

```bash
docker build -f deploy/docker/Dockerfile -t riddle .      # from the repository root
```

| file | what it is |
|---|---|
| `Dockerfile` | three stages: `parakeet-cli` built static from whisper.cpp v1.9.1, the page built with bun, and a python 3.13 image with the package installed |
| `entrypoint.sh` | refuses to start without a password, copies the mounted ssh key into place, fetches the speech model once, seeds a demo, starts the loop in the background and the page in the foreground |
| `compose.yml` | a real server: the tablet over ssh, `riddle.env` for settings |
| `compose.demo.yml` | the demo server: `RIDDLE_DEMO=1`, no tablet, no key. The one App Review signs in to |
| `riddle.env.example` | the settings a container needs; copy to `riddle.env` (gitignored) |

## A real server

1. `cp deploy/docker/riddle.env.example deploy/docker/riddle.env`, and set
   at least `RIDDLE_WEB_PASSWORD`, `RIDDLE_OPENAI_KEY` and `RM2_SSH_HOST`.
2. Put the tablet's key and an ssh config naming it in `deploy/docker/ssh/`
   (gitignored). `riddle setup` on any machine makes both; by hand it is the
   [self-hosting guide](../../docs/self-hosting.md#the-tablet). The tablet
   must be on wifi with ssh on: a container cannot see a USB cable.
3. `docker compose -f deploy/docker/compose.yml up -d --build`
4. Put the agent on the tablet from a machine with zig: `riddle device build`.
   The image does not carry zig.

The app connects to `http://<host>:8765`. Logs: `docker compose logs -f`
for the page, and `/data/log/diary.log` inside the volume for the loop.

What is different in here, on purpose:

- **`RIDDLE_WEB_HOST=0.0.0.0`**, because the port is published by docker,
  and so the entrypoint refuses to start without a password unless
  `RIDDLE_ALLOW_NO_PASSWORD=1` says something else guards it.
- **Nobody supervises the loop but the page.** There is no systemd, so
  `riddle.process.manager` says `here`, and the book in the app starts and
  stops it like on a laptop. A container restart starts it again
  (`RIDDLE_START_DIARY=0` to not).
- **Everything written goes to `/data`**, the volume: the store, the
  photographs, the recordings, the speech model (`RIDDLE_FETCH_MODEL=0` to
  skip the 640 MB download and run without a microphone).

## The demo server

`compose.demo.yml` is a Dokploy compose app on the homelab, beside
`apps/site`, published on the tunnel as `riddle-demo.davideghiotto.it`. Its
two secrets live in Dokploy's environment, never in a file:
`RIDDLE_WEB_PASSWORD` (it goes into the App Review notes) and
`RIDDLE_OPENAI_KEY` (best a separate key with a low monthly cap: anyone with
the password can make it answer).

On start it seeds a few invented pages if its timeline has none. To put it
back as it was after a reviewer has written on it, remove the volume and
redeploy.

It holds no ssh key and `RM2_SSH_HOST` points at a name that cannot resolve,
so even a bug in the demo gate could not reach a tablet.
