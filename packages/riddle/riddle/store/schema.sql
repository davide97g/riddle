-- The diary's memory.
--
-- Two things write here from different processes (the loop, and the web/voice
-- server), so everything is keyed to one clock: milliseconds since the row in
-- `sessions` was written. A monotonic clock does not survive a process
-- boundary, and a wall clock can step under you mid-turn, so both are stored
-- and `t_ms` is the one anything orders by.

PRAGMA journal_mode = WAL;
PRAGMA synchronous  = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;

-- One run of the diary, shared by both halves. Whoever starts first writes
-- the row and the other joins it, because the invariant that matters is one
-- origin for t_ms, not which process owns the session.
--
-- Liveness is the heartbeat, not ended_ms: a process killed outright never
-- gets to set ended_ms, and a session nobody has beaten in a minute is over
-- whatever the row says.
CREATE TABLE IF NOT EXISTS sessions (
  id          INTEGER PRIMARY KEY,
  started_ms  INTEGER NOT NULL,          -- unix epoch ms
  ended_ms    INTEGER,
  note        TEXT,
  loop_ms     INTEGER,                   -- unix epoch ms of the loop's last beat
  voice_ms    INTEGER                    -- and the voice server's
);

-- The timeline. One shape for every kind of thing that happened, so the
-- question "what just went on" is a single query and the model sees one
-- ordering rather than having to merge streams itself.
CREATE TABLE IF NOT EXISTS events (
  id          INTEGER PRIMARY KEY,
  session_id  INTEGER NOT NULL REFERENCES sessions(id),
  kind        TEXT    NOT NULL,          -- strokes|speech|shot|reply|note|tool|error
  t_ms        INTEGER NOT NULL,          -- ms since session start
  dur_ms      INTEGER NOT NULL DEFAULT 0,
  wall_ms     INTEGER NOT NULL,          -- unix epoch ms
  turn        INTEGER,                   -- the turn that claimed it; NULL until claimed
  text        TEXT,                      -- transcript, reply, note; NULL for binary kinds
  path        TEXT,                      -- captures/*.png or audio/*.wav, relative to root
  meta        TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS events_by_time ON events(session_id, t_ms);
CREATE INDEX IF NOT EXISTS events_by_kind ON events(kind, t_ms);
CREATE INDEX IF NOT EXISTS events_by_turn ON events(session_id, turn);

-- Geometry lives apart from the timeline because it is bulk and nothing but
-- the renderer ever wants it. One row per stroke, points packed as
-- little-endian int16 pairs: the screen is 1404x1872 and Device._resample
-- already spaces points 3px apart, so whole pixels lose nothing.
CREATE TABLE IF NOT EXISTS strokes (
  id        INTEGER PRIMARY KEY,
  event_id  INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  seq       INTEGER NOT NULL,
  t_ms      INTEGER NOT NULL,
  points    BLOB    NOT NULL
);
CREATE INDEX IF NOT EXISTS strokes_by_event ON strokes(event_id, seq);

CREATE TABLE IF NOT EXISTS turns (
  id             INTEGER PRIMARY KEY,
  session_id     INTEGER NOT NULL REFERENCES sessions(id),
  n              INTEGER NOT NULL,       -- per-session turn number
  trigger        TEXT    NOT NULL,       -- pause|send
  from_ms        INTEGER NOT NULL,       -- the window of input this turn claims
  to_ms          INTEGER NOT NULL,
  started_ms     INTEGER NOT NULL,
  ended_ms       INTEGER,
  reply          TEXT,
  error          TEXT,
  claude_session TEXT,
  cost_usd       REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS turns_by_n ON turns(session_id, n);

-- The only way another process asks the diary to do something. The loop owns
-- the device pipe; everyone else leaves a note here and waits for it.
CREATE TABLE IF NOT EXISTS intents (
  id          INTEGER PRIMARY KEY,
  session_id  INTEGER REFERENCES sessions(id),
  made_ms  INTEGER NOT NULL,
  source   TEXT    NOT NULL,             -- web|mcp|tool
  action   TEXT    NOT NULL,             -- send|draw|erase|shot|forget
  args     TEXT    NOT NULL DEFAULT '{}',
  state    TEXT    NOT NULL DEFAULT 'pending',  -- pending|running|done|failed
  result   TEXT,
  done_ms  INTEGER
);
CREATE INDEX IF NOT EXISTS intents_pending ON intents(state, id);

-- Search over what was said, written and answered. A tiny corpus today, but
-- LIKE over a growing table with no index is the kind of thing that is fine
-- until it suddenly is not.
CREATE VIRTUAL TABLE IF NOT EXISTS speech_fts
  USING fts5(text, content='events', content_rowid='id');

CREATE TRIGGER IF NOT EXISTS speech_fts_ins AFTER INSERT ON events
  WHEN new.kind IN ('speech', 'note', 'reply') AND new.text IS NOT NULL BEGIN
    INSERT INTO speech_fts(rowid, text) VALUES (new.id, new.text);
  END;

CREATE TRIGGER IF NOT EXISTS speech_fts_del AFTER DELETE ON events
  WHEN old.kind IN ('speech', 'note', 'reply') AND old.text IS NOT NULL BEGIN
    INSERT INTO speech_fts(speech_fts, rowid, text) VALUES ('delete', old.id, old.text);
  END;

-- OF text, not a bare AFTER UPDATE. Claiming a turn writes events.turn on
-- every speech row it takes, and a trigger that did not name its column would
-- rebuild the index entry each time for no reason.
CREATE TRIGGER IF NOT EXISTS speech_fts_upd AFTER UPDATE OF text ON events
  WHEN old.kind IN ('speech', 'note', 'reply') BEGIN
    INSERT INTO speech_fts(speech_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO speech_fts(rowid, text)
      SELECT new.id, new.text WHERE new.text IS NOT NULL
        AND new.kind IN ('speech', 'note', 'reply');
  END;

-- Small shared facts neither half owns: whether a clip is with the speech
-- model right now, when the last one was cut. The loop reads these to know
-- whether waiting a moment longer would catch a sentence still in flight.
CREATE TABLE IF NOT EXISTS state (
  key    TEXT PRIMARY KEY,
  value  TEXT NOT NULL,
  at_ms  INTEGER NOT NULL
);
