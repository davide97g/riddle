"""The diary's memory of one run: sessions, events, strokes, turns, intents.

One sqlite file, written by both halves. `db` holds the whole of it; the
names worth importing are re-exported here.
"""

from riddle.store.db import Store, pack, unpack

__all__ = ["Store", "pack", "unpack"]
