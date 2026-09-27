# The store

One sqlite file, `var/riddle.db`, written by both halves. It is **disposable**:
the schema changes, and deleting the file is a legitimate fix for almost
anything wrong with it. What must survive is in `var/memories.txt`.

## The clock

`sessions.started_ms` is absolute unix epoch milliseconds, written once.
Everything else is `t_ms`, milliseconds since then, which any process can
compute for itself once it has read `started_ms`:

```
t_ms = int(time.time() * 1000) - started_ms
```

A monotonic clock does not survive a process boundary, and a wall clock can
step under you mid-turn, so both are kept: `t_ms` is what anything orders by,
and `wall_ms` is derived back as `started_ms + t_ms` purely so the page can
print a time of day.

Two clocks must never get in: the tablet's monotonic clock, which `riddled`
stamps its samples with, and a browser's `Date.now()`. The loop stamps a
stroke when it takes it off the queue; the page tracks elapsed time from the
`now_ms` the server greeted it with.

## Sessions, and who owns one

Whoever starts first writes the session row; the other joins it. Liveness is
a heartbeat — `loop_ms` and `voice_ms`, beaten every five seconds — and not
`ended_ms`, because a process that is killed outright never gets to write
`ended_ms`. A session nobody has beaten in a minute is over.

A beat therefore outlives the process that made it, for up to that minute,
and the loop refuses to start while another loop looks alive. So **stopping a
half clears its beat** — `Store.gone(role)`, called by `riddle <half> stop` —
and a diary stopped on purpose does not block the next one. A half that was
killed outright still has to wait the window out, which is the conservative
half of the trade.

- `Store.join(path, role)` — the two halves. Never refuses.
- `Store.attach(path)` — a read-only look at whatever is running, or `None`.
  Not an exception: a library cannot know whether "nobody is running" is
  fatal for its caller, and guessing that it was is what used to make the
  voice server start a rival session with a second clock.
- `Store.open(path, note)` — always starts one. For a one-off tool.

## The tables

**`sessions`** — `id`, `started_ms`, `ended_ms`, `note`, `loop_ms`, `voice_ms`.

**`events`** — the timeline. One shape for everything, so "what just went on"
is a single query and the model sees one ordering rather than having to merge
streams itself.

| column | |
|---|---|
| `id` | monotonic; what the page resumes from |
| `kind` | see below |
| `t_ms` | the ordering key |
| `dur_ms` | |
| `wall_ms` | derived, for display only |
| `turn` | the turn that claimed it; NULL until one does |
| `text` | transcript, reply, note |
| `path` | `captures/*.png` or `audio/*.wav`, relative to `var/` |
| `meta` | json |

| kind | written by | carries |
|---|---|---|
| `strokes` | the loop | `path` to the rendered page, `meta.strokes` |
| `speech` | the voice server | `text`, `path` to the clip |
| `note` | the page, or the loop | `text`; `meta.remember` when the diary kept it |
| `reply` | the loop | `text`, `meta.intent` when a send caused it |
| `tool` | the loop | `meta.doing`: opened, thinking, writing, forgetting, cleared, waiting for the tablet, back on the tablet, looking at the whole page |
| `error` | either | `text` |
| `shot` | the loop | `path` to the photograph of the whole page taken before the eraser ran, and the `dur_ms` it took |

**`strokes`** — geometry, kept out of the timeline because it is bulk and
nothing but a renderer wants it. Points are little-endian int16 pairs; the
panel is 1404x1872 and points are already spaced three pixels apart, so whole
pixels lose nothing.

**`turns`** — `n`, `trigger` (`pause` or `send`), the window `from_ms`/`to_ms`,
`reply`, `error`, `claude_session`, `cost_usd`.

**`intents`** — the only way another process asks the diary to do something.
See below.

**`state`** — small shared facts neither half owns. `asr.inflight` is how
the loop knows a sentence is still with the speech model. `diary.vanish` is
the switch on the main page, absent until a page first sets it, which the
loop reads as on. `live.watching` is the wall-clock ms of the newest beat
from a page watching `/live`, or null once the last one left; the loop keeps
its hands off the page while it is under fifteen seconds old. See
[loop.md](loop.md#when-the-diary-keeps-its-hands-off).

**`speech_fts`** — an external-content FTS5 index over `events.text` for
`speech`, `note` and `reply`. Its update trigger is `AFTER UPDATE OF text`
rather than a bare `AFTER UPDATE`, because claiming a turn writes
`events.turn` on every row it takes and an unqualified trigger would rebuild
the index entry each time for nothing.

## Claiming a window

A turn owns a slice of time: `claim(turn, from_ms, to_ms)` marks every
unclaimed `speech` and `note` in that window as belonging to it. This is what
replaces draining a queue, because speech is written by the other process.

The subtlety worth knowing: **what prevents two turns claiming one event is
`turn IS NULL`, not the window.** A transcript is stamped with when it was
*spoken* and written some seconds later, so a sentence can land inside a
window that has already closed. The loop therefore reaches further back than
the previous turn ended — thirty seconds by default, two minutes for a
send — and the `turn IS NULL` filter keeps that safe.

## The intent contract

1. The page pushes: `push_intent("web", "send", {...})`, state `pending`.
2. The loop claims: one atomic `UPDATE ... RETURNING`, so two drainers can
   never be handed the same row. State `running`.
3. The loop finishes: `finish_intent(id, ok=, result=)`. State `done` or
   `failed`.

Rules that keep it honest:

- **A row is never left `running`.** An unknown action is finished as failed
  with a reason, not ignored.
- **Every failed intent also writes an `error` event**, so the page learns
  the outcome through the feed it already tails and never has to poll.
- Only the loop sets `running`, so a `running` row at the loop's startup can
  only be one a previous loop died holding: it is swept to `failed`.
- A pending intent older than two minutes is discarded. A send pressed while
  the tablet was unplugged must not fire when it reconnects.

## Clearing

`Store.clear()` deletes **this session's** `events` and `turns` and returns
the paths those rows named. Strokes go with their event through
`ON DELETE CASCADE` and the FTS index through its delete trigger.

It deletes rather than hiding, because a timeline the page cannot see but
`recall` can still search is two different pasts. It does **not** unlink the
captures or the clips: the store owns a sqlite connection and nothing else,
and a filesystem walk inside a write transaction is exactly what the rule
below forbids. The loop does that, because the loop asked.

Only the loop ever calls it, as the `clear` intent, after it has taken its
ink off the page. The `tool` row it writes afterwards -- `meta.doing` is
`cleared` -- survives the wipe and is how an open page learns that everything
behind it is gone.

## The two rules for writers

**No write transaction is held across a subprocess call, a network wait or a
sleep.** Every write is a single statement, or a handful inside `_tx()` that
touch nothing but the database. With WAL and a five second busy timeout that
is enough; readers never block and the lock is held for microseconds.

**A connection belongs to one thread.** Python's sqlite3 enforces it. Work
that happens off-thread — the model call, a screenshot — posts its result
back and lets the owning thread write.

## Migrations

`executescript` runs `CREATE ... IF NOT EXISTS`, which means **a new column in
`schema.sql` does nothing at all to a database that already exists**; the
first query against it raises `no such column`. So every schema change is
also an entry in `MIGRATIONS` in `riddle/store/db.py`, applied in order and
remembered in `PRAGMA user_version`. A fresh file is stamped as current
without running any of them.
