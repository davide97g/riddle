"""A few invented pages, for a demo server's timeline to open on.

Somebody signing in to a `RIDDLE_DEMO` server -- App Review, mostly -- should
see what the app is for before they have written anything: a question in a
hand, the diary's answer under it, a line it chose to keep. These are those,
written into the store the way the loop would have written them, so every
row is one the clients already know how to draw.

They are invented, and only ever written where `RIDDLE_DEMO` is set: a real
diary's timeline is a record of what somebody actually wrote, and this must
not be able to slip a made-up page into one.

The questions are in a Hershey script, the same stand-in for a person's hand
the landing page uses (apps/site/tools/make_strokes.py); the replies are the
diary's own, as text.
"""

import time

from riddle import config, paths

# (what was written or said, how, the diary's answer)
PAGES = [
    ("who are you?", "ink", "Someone who keeps your pages."),
    ("what should I write?", "ink", "Whatever you would not *say*."),
    ("remind me what I wanted to read this winter", "voice",
     "The long Russian one you keep moving to the bottom of the pile."),
]
KEPT = "Reads on the train in the morning; mentions a long novel they keep avoiding."

QUESTION_HEIGHT = 120


def _ink(text: str):
    from riddle.ink import hershey
    from riddle.ink.geometry import SCREEN_W

    font = hershey.Font("scripts")
    runs = [hershey.Run(text, font, QUESTION_HEIGHT)]
    return [
        [(x, y) for x, y in line]
        for line in hershey.layout_runs(
            runs, center_x=SCREEN_W / 2, baseline=520, max_width=SCREEN_W - 260
        )
        if len(line) > 1
    ]


def seed() -> int:
    from riddle.ink import render
    from riddle.store import Store

    cfg = config.get()
    if not cfg.demo:
        print("refusing: these pages are invented, and only a RIDDLE_DEMO server may hold them")
        return 1
    paths.ensure()
    store = Store.join(cfg.db, "seed")
    try:
        if store.recent(kinds=["reply"], limit=1):
            print(f"session {store.session_id} already has pages; leaving it")
            return 0
        for turn, (said, how, reply) in enumerate(PAGES, 1):
            t = store.now_ms()
            if how == "ink":
                strokes = _ink(said)
                times = [(t + i * 120, t + i * 120 + 100) for i in range(len(strokes))]
                image = render.strokes_to_png(
                    strokes, paths.CAPTURES / f"page-{int(time.time())}-demo{turn}.png"
                )
                store.add_strokes(strokes, times, turn=turn,
                                  path=paths.relative(image, paths.VAR),
                                  meta={"during_answer": False})
            else:
                store.add_event("speech", turn=turn, text=said, dur_ms=2400)
            store.begin_turn(turn, "pause" if how == "ink" else "send", -1, store.now_ms())
            store.add_event("reply", turn=turn, text=reply)
            store.end_turn(turn, reply=reply)
        store.add_event("note", text=KEPT, meta={"remember": True})
        print(f"wrote {len(PAGES)} invented pages into session {store.session_id}")
        return 0
    finally:
        store.close()
