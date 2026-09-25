"""The diary's memory: one sqlite file, written by both halves.

The loop and the voice server both write here, so there is one rule that
keeps them out of each other's way: **no write transaction is held
across a subprocess call, a network wait or a sleep**. Every write below is a
single statement, or a handful inside `_tx()` that touch nothing but the
database. With WAL and a five second busy timeout, that is enough; readers
never block and the write lock is held for microseconds. The corollary is
just as load bearing: **a connection belongs to one thread**. Python's
sqlite3 enforces it, so anything that does slow work off-thread posts its
result back and lets the owning thread write.

Time is the other shared thing. `t_ms` is milliseconds since the session row
was written, which any process can compute for itself once it knows
`started_ms`. `time.monotonic()` does not survive a process boundary, and a
wall clock can step mid-turn, so both are stored and `t_ms` is what anything
orders by.
"""

import json
import sqlite3
import struct
import time
from contextlib import contextmanager
from pathlib import Path

from riddle.paths import SCHEMA

# Anything that can be on the timeline. Checked in Python rather than as a
# column constraint, because adding one to an existing table means rebuilding
# it, and the value here is catching a typo at the call site.
KINDS = ("strokes", "speech", "shot", "reply", "note", "tool", "error")

# A session nobody has beaten in this long is over, whatever ended_ms says:
# a process that was killed outright never got to write it.
STALE_MS = 60_000

# The schema is applied with CREATE ... IF NOT EXISTS, which means a new
# column in schema.sql does nothing at all to a database that already exists
# -- the first query against it simply raises "no such column". So each
# change is also a migration, applied in order and remembered in
# PRAGMA user_version.
MIGRATIONS = (
    # 1: both halves may now start a session, so each beats its own clock.
    ("ALTER TABLE sessions ADD COLUMN loop_ms INTEGER",
     "ALTER TABLE sessions ADD COLUMN voice_ms INTEGER"),
    # 2: made_ms is session-relative, so an intent has to say which session.
    ("ALTER TABLE intents ADD COLUMN session_id INTEGER REFERENCES sessions(id)",),
)

# The panel is 1404x1872 and Device._resample already spaces points three
# pixels apart, so rounding to whole pixels throws away nothing a pen could
# have drawn. Anything outside the panel is a bug upstream; clamp rather than
# raise, because losing a turn to a stray coordinate would be worse.
LIMIT = 32767


def pack(points) -> bytes:
    flat = []
    for x, y in points:
        flat.append(max(-LIMIT, min(LIMIT, round(x))))
        flat.append(max(-LIMIT, min(LIMIT, round(y))))
    return struct.pack(f"<{len(flat)}h", *flat)


def unpack(blob: bytes) -> list[tuple[int, int]]:
    flat = struct.unpack(f"<{len(blob) // 2}h", blob)
    return list(zip(flat[0::2], flat[1::2]))


class Store:
    """One connection, owned by one thread. Never share it between threads."""

    def __init__(self, conn: sqlite3.Connection, session_id: int, started_ms: int) -> None:
        self.conn = conn
        self.session_id = session_id
        self.started_ms = started_ms
        self.role = "reader"

    @classmethod
    def open(cls, path: Path, note: str | None = None) -> "Store":
        """Open the store and start a session of its own."""
        conn = _connect(path)
        started_ms = int(time.time() * 1000)
        row = conn.execute(
            "INSERT INTO sessions (started_ms, note) VALUES (?, ?) RETURNING id",
            (started_ms, note),
        ).fetchone()
        return cls(conn, row["id"], started_ms)

    @classmethod
    def join(cls, path: Path, role: str) -> "Store":
        """Join the session in progress, or start one. Never refuses.

        Strict ownership -- the loop creates, everyone else attaches -- fails
        in the case that actually happens: the page is meant to be usable
        before the tablet is connected. So whoever arrives first writes the
        session row and the second one joins it, and the shared clock is
        preserved either way round.
        """
        conn = _connect(path)
        cutoff = int(time.time() * 1000) - STALE_MS
        row = conn.execute(
            "SELECT id, started_ms FROM sessions WHERE ended_ms IS NULL"
            " AND max(coalesce(loop_ms, 0), coalesce(voice_ms, 0)) > ?"
            " ORDER BY id DESC LIMIT 1",
            (cutoff,),
        ).fetchone()
        if row is None:
            started_ms = int(time.time() * 1000)
            row = conn.execute(
                "INSERT INTO sessions (started_ms, note) VALUES (?, ?)"
                " RETURNING id, started_ms",
                (started_ms, role),
            ).fetchone()
        store = cls(conn, row["id"], row["started_ms"])
        store.role = role
        store.beat()
        return store

    @classmethod
    def attach(cls, path: Path) -> "Store | None":
        """Join a live session read-only, or None if nothing is running.

        None rather than an exception: a library cannot know whether "nobody
        is running" is fatal for its caller, and guessing that it was is what
        used to make the voice server give up and start a rival session.
        """
        conn = _connect(path)
        cutoff = int(time.time() * 1000) - STALE_MS
        row = conn.execute(
            "SELECT id, started_ms FROM sessions WHERE ended_ms IS NULL"
            " AND max(coalesce(loop_ms, 0), coalesce(voice_ms, 0)) > ?"
            " ORDER BY id DESC LIMIT 1",
            (cutoff,),
        ).fetchone()
        if row is None:
            conn.close()
            return None
        return cls(conn, row["id"], row["started_ms"])

    def beat(self) -> None:
        """Say this half is still here. One statement, called every few seconds."""
        column = "loop_ms" if self.role == "loop" else "voice_ms"
        self.conn.execute(
            f"UPDATE sessions SET {column} = ? WHERE id = ?",
            (int(time.time() * 1000), self.session_id),
        )

    def gone(self, role: str) -> None:
        """Take a half's heartbeat out, because it was stopped on purpose.

        A beat sits in the row looking alive for the whole stale window, and a
        new loop refuses to start while another loop looks alive. That made
        `riddle start` fail for a minute after a stop. Whoever did the
        stopping knows better than the clock does; this is it saying so.

        Both ends say it now. `close()` calls this for its own role, because
        the half that is dying knows soonest -- and under systemd there is no
        `riddle ... stop` in the picture at all, only a SIGTERM and, half a
        second later, a replacement refusing to start.
        """
        column = "loop_ms" if role == "loop" else "voice_ms"
        self.conn.execute(
            f"UPDATE sessions SET {column} = NULL WHERE id = ?", (self.session_id,)
        )

    def present(self, role: str) -> int | None:
        """How long ago the other half last said it was there, in ms."""
        column = "loop_ms" if role == "loop" else "voice_ms"
        row = self.conn.execute(
            f"SELECT {column} AS beat FROM sessions WHERE id = ?", (self.session_id,)
        ).fetchone()
        if row is None or row["beat"] is None:
            return None
        ago_ms = int(time.time() * 1000) - row["beat"]
        return ago_ms if ago_ms < STALE_MS else None

    def now_ms(self) -> int:
        return int(time.time() * 1000) - self.started_ms

    def close(self) -> None:
        """Say this half is gone, and end the session only if it was the last.

        Ending it while the other half is still beating splits them: `join`
        will not touch a session with an `ended_ms`, so the survivor keeps
        writing into a row the newcomer cannot join, and the page and the loop
        end up in different sessions with different clocks. That is exactly
        what a `systemctl restart riddle-diary` does.

        A reader never ends anything. It only ever looked.
        """
        if self.role not in ("loop", "voice"):
            self.conn.close()
            return
        self.gone(self.role)
        other = "voice" if self.role == "loop" else "loop"
        if self.present(other) is None:
            self.conn.execute(
                "UPDATE sessions SET ended_ms = ? WHERE id = ?",
                (int(time.time() * 1000), self.session_id),
            )
        self.conn.close()

    @contextmanager
    def _tx(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    # --- writing ---------------------------------------------------------

    def add_event(
        self,
        kind: str,
        *,
        t_ms: int | None = None,
        dur_ms: int = 0,
        turn: int | None = None,
        text: str | None = None,
        path: str | None = None,
        meta: dict | None = None,
    ) -> int:
        if kind not in KINDS:
            raise ValueError(f"unknown event kind {kind!r}")
        t_ms = self.now_ms() if t_ms is None else t_ms
        row = self.conn.execute(
            "INSERT INTO events (session_id, kind, t_ms, dur_ms, wall_ms, turn, text, path, meta)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
            (
                self.session_id,
                kind,
                t_ms,
                dur_ms,
                self.started_ms + t_ms,
                turn,
                text,
                path,
                json.dumps(meta or {}),
            ),
        ).fetchone()
        return row["id"]

    def add_strokes(
        self,
        strokes: list[list[tuple[float, float]]],
        times: list[tuple[int, int]],
        *,
        turn: int | None = None,
        path: str | None = None,
        meta: dict | None = None,
    ) -> int:
        """Record a batch of strokes as one timeline event plus its geometry.

        `times[i]` is the (first sample, pen up) pair for `strokes[i]`, so the
        event spans from the first mark to the last lift.
        """
        if not strokes:
            raise ValueError("no strokes")
        t0 = times[0][0]
        meta = dict(meta or {})
        meta.setdefault("strokes", len(strokes))
        with self._tx():
            event_id = self.add_event(
                "strokes",
                t_ms=t0,
                dur_ms=times[-1][1] - t0,
                turn=turn,
                path=path,
                meta=meta,
            )
            self.conn.executemany(
                "INSERT INTO strokes (event_id, seq, t_ms, points) VALUES (?, ?, ?, ?)",
                [
                    (event_id, i, times[i][0], pack(stroke))
                    for i, stroke in enumerate(strokes)
                ],
            )
        return event_id

    def stroke_geometry(self, event_id: int) -> list[list[tuple[int, int]]]:
        rows = self.conn.execute(
            "SELECT points FROM strokes WHERE event_id = ? ORDER BY seq", (event_id,)
        ).fetchall()
        return [unpack(row["points"]) for row in rows]

    # --- turns -----------------------------------------------------------

    def begin_turn(self, n: int, trigger: str, from_ms: int, to_ms: int) -> None:
        self.conn.execute(
            "INSERT INTO turns (session_id, n, trigger, from_ms, to_ms, started_ms)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (self.session_id, n, trigger, from_ms, to_ms, self.now_ms()),
        )

    def end_turn(
        self,
        n: int,
        *,
        reply: str | None = None,
        error: str | None = None,
        claude_session: str | None = None,
        cost_usd: float | None = None,
    ) -> None:
        self.conn.execute(
            "UPDATE turns SET ended_ms = ?, reply = ?, error = ?, claude_session = ?,"
            " cost_usd = ? WHERE session_id = ? AND n = ?",
            (self.now_ms(), reply, error, claude_session, cost_usd, self.session_id, n),
        )

    def claim(self, turn: int, from_ms: int, to_ms: int, kinds=("speech", "note")) -> int:
        """Mark unclaimed input in a window as belonging to this turn.

        This is what replaces draining a queue. Speech is written by another
        process, so the loop cannot take it off a queue; instead a turn owns a
        slice of time, and anything recorded after that slice is the next
        turn's business whoever wrote it.

        The window is half open, `from_ms` exclusive, and the first turn of a
        session starts from -1 rather than 0. But what really prevents two
        turns claiming one event is `turn IS NULL`, not the window -- which
        matters, because a transcript is stamped with when it was *spoken* and
        can be written some seconds later, after the window it belongs to has
        closed. The caller is therefore free to reach further back than the
        previous turn ended, and does.
        """
        marks = ",".join("?" * len(kinds))
        done = self.conn.execute(
            f"UPDATE events SET turn = ? WHERE session_id = ? AND turn IS NULL"
            f" AND kind IN ({marks}) AND t_ms > ? AND t_ms <= ?",
            (turn, self.session_id, *kinds, from_ms, to_ms),
        )
        return done.rowcount

    def clear(self) -> list[str]:
        """Wipe this session's timeline, and name the files it orphaned.

        The eraser on the page means the conversation did not happen, so the
        rows go rather than being hidden behind a marker: a timeline the page
        cannot see but `recall` still searches is two different pasts.

        What is *not* deleted here is the files those rows named. The store
        owns one sqlite connection and nothing else; whoever asked for the
        wipe unlinks the captures and the clips, so a slow filesystem can
        never hold a write transaction open.
        """
        files = [
            row["path"]
            for row in self.conn.execute(
                "SELECT path FROM events WHERE session_id = ? AND path IS NOT NULL",
                (self.session_id,),
            ).fetchall()
        ]
        with self._tx():
            # strokes hang off events with ON DELETE CASCADE, and the fts
            # index is kept by the delete trigger; both follow from this.
            self.conn.execute("DELETE FROM events WHERE session_id = ?", (self.session_id,))
            self.conn.execute("DELETE FROM turns WHERE session_id = ?", (self.session_id,))
        return files

    # --- reading ---------------------------------------------------------

    def recent(
        self,
        *,
        since_ms: int | None = None,
        kinds: list[str] | None = None,
        limit: int = 40,
        turn: int | None = None,
    ) -> list[dict]:
        where = ["session_id = ?"]
        args: list = [self.session_id]
        if since_ms is not None:
            where.append("t_ms > ?")
            args.append(since_ms)
        if turn is not None:
            where.append("turn = ?")
            args.append(turn)
        if kinds:
            where.append(f"kind IN ({','.join('?' * len(kinds))})")
            args.extend(kinds)
        rows = self.conn.execute(
            f"SELECT * FROM events WHERE {' AND '.join(where)}"
            f" ORDER BY t_ms DESC LIMIT ?",
            (*args, limit),
        ).fetchall()
        return [_event(row) for row in reversed(rows)]

    def since_id(self, event_id: int, limit: int = 200) -> list[dict]:
        """Everything newer than an id. How the web server tails the store."""
        rows = self.conn.execute(
            "SELECT * FROM events WHERE session_id = ? AND id > ? ORDER BY id LIMIT ?",
            (self.session_id, event_id, limit),
        ).fetchall()
        return [_event(row) for row in rows]

    def search(self, query: str, *, before_ms: int | None = None, limit: int = 10) -> list[dict]:
        rows = self.conn.execute(
            "SELECT events.* FROM speech_fts JOIN events ON events.id = speech_fts.rowid"
            " WHERE speech_fts MATCH ? AND events.session_id = ?"
            " AND (? IS NULL OR events.t_ms < ?)"
            " ORDER BY events.t_ms DESC LIMIT ?",
            (query, self.session_id, before_ms, before_ms, limit),
        ).fetchall()
        return [_event(row) for row in rows]

    # --- intents ---------------------------------------------------------

    def push_intent(self, source: str, action: str, args: dict | None = None) -> int:
        row = self.conn.execute(
            "INSERT INTO intents (session_id, made_ms, source, action, args)"
            " VALUES (?, ?, ?, ?, ?) RETURNING id",
            (self.session_id, self.now_ms(), source, action, json.dumps(args or {})),
        ).fetchone()
        return row["id"]

    def intent_waiting(self) -> bool:
        """Is there anything to do? A cheap indexed read, run several times a
        second, so that the common case of an empty queue never takes the
        write lock the voice server is using to record speech."""
        row = self.conn.execute(
            "SELECT 1 FROM intents WHERE state = 'pending' AND session_id = ? LIMIT 1",
            (self.session_id,),
        ).fetchone()
        return row is not None

    def claim_intent(self) -> dict | None:
        """Take the oldest pending intent of this session, atomically.

        One UPDATE rather than a SELECT then an UPDATE, so two processes
        draining the queue can never hand out the same row.
        """
        row = self.conn.execute(
            "UPDATE intents SET state = 'running' WHERE id = ("
            "  SELECT id FROM intents WHERE state = 'pending' AND session_id = ?"
            "  ORDER BY id LIMIT 1"
            ") RETURNING id, source, action, args, made_ms",
            (self.session_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "source": row["source"],
            "action": row["action"],
            "args": json.loads(row["args"]),
            "made_ms": row["made_ms"],
        }

    def abandon_intents(self, reason: str) -> int:
        """Fail anything left `running`. Only the loop ever sets that state,
        so at its startup a running row can only be one it died holding."""
        done = self.conn.execute(
            "UPDATE intents SET state = 'failed', result = ?, done_ms = ?"
            " WHERE state = 'running'",
            (json.dumps({"error": reason}), self.now_ms()),
        )
        return done.rowcount

    def expire_intents(self, older_than_ms: int, reason: str) -> list[int]:
        """Discard pending intents nobody served in time.

        A send pressed forty minutes ago, while the tablet was unplugged, must
        not fire the moment it connects.
        """
        rows = self.conn.execute(
            "UPDATE intents SET state = 'failed', result = ?, done_ms = ?"
            " WHERE state = 'pending' AND made_ms < ? RETURNING id",
            (json.dumps({"error": reason}), self.now_ms(), older_than_ms),
        ).fetchall()
        return [row["id"] for row in rows]

    def finish_intent(self, intent_id: int, *, ok: bool = True, result=None) -> None:
        self.conn.execute(
            "UPDATE intents SET state = ?, result = ?, done_ms = ? WHERE id = ?",
            ("done" if ok else "failed", json.dumps(result), self.now_ms(), intent_id),
        )

    # --- small shared facts ----------------------------------------------

    def set_state(self, key: str, value) -> None:
        self.conn.execute(
            "INSERT INTO state (key, value, at_ms) VALUES (?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value, at_ms = excluded.at_ms",
            (key, json.dumps(value), self.now_ms()),
        )

    def get_state(self, key: str, default=None):
        row = self.conn.execute(
            "SELECT value FROM state WHERE key = ?", (key,)
        ).fetchone()
        return json.loads(row["value"]) if row else default

    # --- whether the diary may write on the page -------------------------

    def vanish(self) -> bool | None:
        """Whether the diary takes the ink off and answers, as the page set it.

        `None` until somebody has set it, which the loop reads as yes: that
        is what the diary always did, and a page that has never been opened
        should not quietly change it.
        """
        value = self.get_state("diary.vanish")
        return value if isinstance(value, bool) else None

    def set_vanish(self, on: bool) -> None:
        self.set_state("diary.vanish", bool(on))

    def watching(self, on: bool) -> None:
        """Say a page is watching the tablet live, or that the last one left.

        Wall-clock ms, like the heartbeats in `sessions`, so it outlives a
        session change, and refreshed every few seconds rather than set once:
        a voice server that dies with a page open must not keep the diary's
        hands off the page for ever.
        """
        self.set_state("live.watching", int(time.time() * 1000) if on else None)

    def watched(self, within_ms: int) -> bool:
        seen = self.get_state("live.watching")
        return isinstance(seen, int) and 0 <= time.time() * 1000 - seen < within_ms

    def intent(self, intent_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT id, state, result FROM intents WHERE id = ?", (intent_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "state": row["state"],
            "result": json.loads(row["result"]) if row["result"] else None,
        }


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.exists()
    # Autocommit, so a transaction only exists where _tx() puts one. The
    # alternative is python opening one behind your back before the first
    # INSERT and holding it until something remembers to commit.
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA.read_text())
    _migrate(conn, fresh)
    return conn


def _migrate(conn: sqlite3.Connection, fresh: bool) -> None:
    """Bring an older database up to the schema it was just handed.

    executescript only creates what is missing, so a column added to an
    existing table needs saying twice: once in schema.sql for a new database
    and once here for one that already exists. A fresh file is stamped as
    current without running anything.
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if fresh:
        conn.execute(f"PRAGMA user_version = {len(MIGRATIONS)}")
        return
    for step, statements in enumerate(MIGRATIONS[version:], start=version + 1):
        for statement in statements:
            try:
                conn.execute(statement)
            except sqlite3.OperationalError as exc:
                # A column the schema already created on a database that was
                # made between two versions. Nothing to do.
                if "duplicate column name" not in str(exc):
                    raise
        conn.execute(f"PRAGMA user_version = {step}")


def _event(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "t_ms": row["t_ms"],
        "dur_ms": row["dur_ms"],
        "wall_ms": row["wall_ms"],
        "turn": row["turn"],
        "text": row["text"],
        "path": row["path"],
        "meta": json.loads(row["meta"]),
    }


def ago(t_ms: int, now_ms: int) -> str:
    """How long ago, in words. Models reason about this far better than ints."""
    s = max(0, now_ms - t_ms) / 1000
    if s < 1:
        return "just now"
    if s < 60:
        return f"{int(s)} seconds ago"
    if s < 3600:
        return f"{int(s // 60)} minutes ago"
    return f"{int(s // 3600)} hours ago"
