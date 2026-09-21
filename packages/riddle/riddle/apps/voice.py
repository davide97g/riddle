#!/usr/bin/env python3
"""The other half of the diary: a page you can speak into.

Run this alongside the loop. It records what is said into the same store the
loop writes strokes to, and asks for a turn by leaving an intent the loop
picks up. It never opens an ssh connection and never draws: the two halves
share a file, not a device, which is why there is no lock anywhere here and
no second Device.

The server binds loopback only. `riddle voice share` puts a real certificate
in front of it, which is not decoration: a browser will not hand out a
microphone to a page that is not a secure context, and a lan address over
plain http is not one.
"""

import asyncio
import sys

from riddle import config, paths
from riddle.voice import ears as ears_module
from riddle.store import Store
from riddle.web import server as web

BEAT_S = 5.0


async def heartbeat(store) -> None:
    """Say this half is still here, so the loop and the page can both tell."""
    while True:
        await asyncio.sleep(BEAT_S)
        try:
            store.beat()
        except Exception as exc:  # noqa: BLE001 - a missed beat is not fatal
            print(f"heartbeat failed: {exc}", file=sys.stderr)


async def main() -> None:
    cfg = config.get()
    paths.ensure()

    # Whoever starts first writes the session row; the other joins it. The
    # page is meant to be usable before the tablet is connected, so refusing
    # to start without the loop would be the wrong way round.
    memory = Store.join(cfg.db, "voice")
    if memory.present("loop") is not None:
        print(f"joined the diary's session {memory.session_id}", file=sys.stderr)
    else:
        print(
            f"session {memory.session_id}; the diary is not running, so a send "
            f"will wait rather than be answered",
            file=sys.stderr,
        )

    ears = ears_module.Ears(memory, paths.VAR)
    ears.prune()
    model = ears_module.model_path()
    if not model.is_file():
        print(f"no speech model at {model}: the page will run without a mic", file=sys.stderr)
        ears = None

    server = web.Server(memory, paths.VAR, cfg.web_dir, ears)
    if ears is not None:
        # The ears talk back to whoever is watching -- the level meter, and
        # the row that says a sentence is being read.
        ears.hub = server.hub

    listening = await asyncio.start_server(server.handle, cfg.web_host, cfg.web_port)
    built = f"serving {paths.relative(cfg.web_dir)}" if cfg.web_dir.is_dir() else "no build yet, api only"
    print(f"listening on http://{cfg.web_host}:{cfg.web_port} ({built})", file=sys.stderr)
    print("run `riddle voice share` to reach it from a phone", file=sys.stderr)

    async with listening:
        await asyncio.gather(
            listening.serve_forever(), server.hub.tail(), heartbeat(memory)
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
