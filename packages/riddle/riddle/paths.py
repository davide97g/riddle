"""Where everything is, worked out once.

Before this module the repository root was guessed in eight different places
by counting `.parent`s up from a file, which meant that moving any file
quietly moved `captures/`, `memories.txt` or the database with it. The
failures were invisible: sqlite makes a new empty file rather than
complaining, and a missing memory file reads as a diary that has forgotten
you.

So the root is found by looking for a marker rather than by counting, and
everything the diary writes lives under one directory, `var/`, which is
gitignored whole and safe to delete when it gets embarrassing.
"""

import os
from pathlib import Path

MARKERS = (".env.example", "packages/riddle/pyproject.toml")


def _find_root() -> Path:
    """Walk up from this file until the repository announces itself.

    An editable install means this module really does sit inside the tree, so
    walking works -- but hard-coding the number of levels would be the same
    fragility this module exists to remove.
    """
    override = os.environ.get("RIDDLE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if all((parent / name).exists() for name in MARKERS):
            return parent
    raise RuntimeError(
        f"cannot find the riddle checkout above {here}: no directory holds "
        f"{' and '.join(MARKERS)}. Set RIDDLE_ROOT to point at it."
    )


ROOT = _find_root()

# Everything the diary writes. One directory, one gitignore rule, one answer
# to "what is safe to delete".
VAR = Path(os.environ.get("RIDDLE_VAR", ROOT / "var")).resolve()
CAPTURES = VAR / "captures"      # photographs of the page, sent to the model
AUDIO = VAR / "audio"            # utterances cut out of the microphone
MODELS = VAR / "models"          # the speech model, fetched once by hand
RUN = VAR / "run"                # pidfiles
LOG = VAR / "log"
BUILD = VAR / "build"            # the cross-compiled agent
BACKUPS = VAR / "backups"        # tablet snapshots: private keys, notebooks

MEMORIES = VAR / "memories.txt"  # what survives a page turn
SESSION = VAR / "session"        # the resumed Claude Code session id

# Tracked, not state: taps.json is calibration for this tablet's toolbar and
# belongs in the repository.
TAPS = ROOT / "taps.json"

WEB_DIR = ROOT / "apps" / "web" / "dist"

# Package data, which sits beside the code that reads it. Derived from this
# module's own location rather than through importlib.resources, because the
# store package imports this module and asking importlib for it would close
# the circle. One spelling each is the point; this is not a root guess.
PACKAGE = Path(__file__).resolve().parent
FONT_DIR = PACKAGE / "ink" / "fonts"
SCHEMA = PACKAGE / "store" / "schema.sql"

DIRS = (CAPTURES, AUDIO, MODELS, RUN, LOG, BUILD, BACKUPS)


def ensure() -> None:
    """Make the state directories. Cheap, idempotent, called from the CLI."""
    for path in DIRS:
        path.mkdir(parents=True, exist_ok=True)


def under_root(value: str | Path, base: Path = ROOT) -> Path:
    """Resolve a configured path: absolute wins, relative hangs off `base`."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def relative(path: Path) -> str:
    """How a path is written into the store: relative to the root, if it can be."""
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def env(name: str, default: str) -> str:
    """The one environment read that predates riddle.config, kept for it."""
    return os.environ.get(name, default)
