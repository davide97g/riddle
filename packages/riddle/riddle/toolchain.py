"""How the client's toolchain is invoked, worked out once.

vite.config.ts reads RIDDLE_SERVER and RIDDLE_TAILNET out of its environment
rather than being told where the python server is, so something has to put
them there. Two callers need that now -- `riddle web` and `riddle dev` -- and
a second spelling of the environment is a second place for the dev proxy to
drift away from the port the server actually binds.
"""

import os
import shutil

from riddle import paths

WHERE = paths.ROOT / "apps" / "web"

MISSING = "bun is not installed: brew install oven-sh/bun/bun"


def have_bun() -> bool:
    return shutil.which("bun") is not None


def env(*, tailnet: bool = False) -> dict[str, str]:
    """The environment vite.config.ts expects, on top of this one."""
    from riddle import config

    cfg = config.get()
    return {
        **os.environ,
        "RIDDLE_SERVER": cfg.server,
        "RIDDLE_TAILNET": "1" if (cfg.tailnet or tailnet) else "0",
    }
