"""The diary's memory: one sqlite file, written by three processes.

The loop, the web server and the MCP server all write here, so there is one
rule that keeps them out of each other's way: **no write transaction is held
across a subprocess call, a network wait or a sleep**. Every write below is a
single statement, or a handful inside `_tx()` that touch nothing but the
database. With WAL and a five second busy timeout, that is enough; readers
never block and the write lock is held for microseconds.

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

SCHEMA = Path(__file__).resolve().parent / "schema.sql"

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

    @classmethod
    def open(cls, path: Path, note: str | None = None) -> "Store":
        """Open the store and start a session."""
        conn = _connect(path)
        started_ms = int(time.time() * 1000)
        row = conn.execute(
            "INSERT INTO sessions (started_ms, note) VALUES (?, ?) RETURNING id",
            (started_ms, note),
        ).fetchone()
        return cls(conn, row["id"], started_ms)

    @classmethod
    def attach(cls, path: Path) -> "Store":
        """Open the store and join the session already running.

        The web server and the MCP server do this: they record into whatever
        session the loop started, and refuse to invent one of their own, because
        a second session would give every timestamp a different origin.
        """
        conn = _connect(path)
        row = conn.execute(
            "SELECT id, started_ms FROM sessions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            raise RuntimeError(f"no session in {path}: start the diary first")
        return cls(conn, row["id"], row["started_ms"])

    def now_ms(self) -> int:
        return int(time.time() * 1000) - self.started_ms

    def close(self) -> None:
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
                "strokes", t_ms=t0, dur_ms=times[-1][1] - t0, turn=turn, meta=meta
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

        The window is half open, `from_ms` exclusive, so consecutive turns
        cannot both claim the same event. The first turn of a session
        therefore starts from -1, not 0.
        """
        marks = ",".join("?" * len(kinds))
        done = self.conn.execute(
            f"UPDATE events SET turn = ? WHERE session_id = ? AND turn IS NULL"
            f" AND kind IN ({marks}) AND t_ms > ? AND t_ms <= ?",
            (turn, self.session_id, *kinds, from_ms, to_ms),
        )
        return done.rowcount

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
            "INSERT INTO intents (made_ms, source, action, args) VALUES (?, ?, ?, ?)"
            " RETURNING id",
            (self.now_ms(), source, action, json.dumps(args or {})),
        ).fetchone()
        return row["id"]

    def claim_intent(self) -> dict | None:
        """Take the oldest pending intent, atomically.

        One UPDATE rather than a SELECT then an UPDATE, so two processes
        draining the queue can never hand out the same row.
        """
        row = self.conn.execute(
            "UPDATE intents SET state = 'running' WHERE id = ("
            "  SELECT id FROM intents WHERE state = 'pending' ORDER BY id LIMIT 1"
            ") RETURNING id, source, action, args"
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "source": row["source"],
            "action": row["action"],
            "args": json.loads(row["args"]),
        }

    def finish_intent(self, intent_id: int, *, ok: bool = True, result=None) -> None:
        self.conn.execute(
            "UPDATE intents SET state = ?, result = ?, done_ms = ? WHERE id = ?",
            ("done" if ok else "failed", json.dumps(result), self.now_ms(), intent_id),
        )

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
    if fresh:
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


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
