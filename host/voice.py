#!/usr/bin/env python3
"""The other half of the diary: a page you can speak into.

Run this alongside the loop. It records what is said into the same store the
loop writes strokes to, and asks for a turn by leaving an intent the loop picks
up. It never opens an ssh connection and never draws.

The server binds loopback only. `tailscale serve` puts a real certificate in
front of it, which is not decoration: a browser will not hand out a microphone
to a page that is not a secure context, and a lan address over plain http is
not one.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ears as ears_module
import store
import web

ROOT = Path(__file__).resolve().parent.parent


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


async def main() -> None:
    db = ROOT / env("RIDDLE_DB", "riddle.db")
    try:
        memory = store.Store.attach(db)
        print(f"joined session {memory.session_id}", file=sys.stderr)
    except (RuntimeError, FileNotFoundError):
        # The loop has not recorded anything yet, so there is no session to
        # share a clock with. Start one rather than refuse: the page is worth
        # having up before the tablet is.
        memory = store.Store.open(db, note="voice")
        print(
            f"no session yet, started {memory.session_id} "
            f"(start the diary and restart this to share its clock)",
            file=sys.stderr,
        )

    ears = ears_module.Ears(memory, ROOT)
    ears.prune()
    model = ears_module.model_path()
    if not (model if model.is_absolute() else ROOT / model).is_file():
        print(f"no speech model at {model}: the page will run without a mic", file=sys.stderr)
        ears = None

    web_dir = ROOT / env("RIDDLE_WEB_DIR", "web/dist")
    server = web.Server(memory, ROOT, web_dir, ears)
    if ears is not None:
        # The ears talk back to whoever is watching -- the level meter, and
        # the row that says a sentence is being read.
        ears.hub = server.hub

    host = env("RIDDLE_WEB_HOST", "127.0.0.1")
    port = int(env("RIDDLE_WEB_PORT", "8765"))
    listening = await asyncio.start_server(server.handle, host, port)
    built = "serving web/dist" if web_dir.is_dir() else "no build yet, api only"
    print(f"listening on http://{host}:{port} ({built})", file=sys.stderr)
    print("run `tailscale serve --bg %d` to reach it from a phone" % port, file=sys.stderr)

    async with listening:
        await asyncio.gather(listening.serve_forever(), server.hub.tail())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
