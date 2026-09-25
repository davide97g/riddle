import type { DiaryEvent, DiaryPresence, Row, ServerMessage } from '@/lib/protocol'

export type Conn = 'connecting' | 'open' | 'closed'

export type State = {
  /** highest event id applied, and what `hello` resumes from */
  seq: number
  rows: Map<string, Row>
  /** row ids, kept sorted by t_ms */
  order: string[]
  session: number | null
  startedMs: number | null
  /** the server's own t_ms when it greeted us, and the local clock reading at
   *  that moment. A phone whose clock is a few seconds off the Mac's would
   *  otherwise drop its own rows into the wrong place in a list sorted by
   *  t_ms, so elapsed time is measured rather than assumed. */
  serverNowMs: number | null
  greetedAt: number | null
  listening: boolean
  /** whether the server will stream the tablet's screen */
  live: boolean
  /** whether the half that owns the pen is running */
  diary: DiaryPresence
  conn: Conn
  draft: string
  /** somebody is speaking right now */
  hearing: boolean
  /** clips the model is still working through */
  reading: string[]
}

export const initial: State = {
  seq: 0,
  rows: new Map(),
  order: [],
  session: null,
  startedMs: null,
  serverNowMs: null,
  greetedAt: null,
  listening: false,
  live: false,
  diary: { present: false, ago_ms: null, manager: 'here', busy: false },
  conn: 'connecting',
  draft: '',
  hearing: false,
  reading: [],
}

export type Action =
  | { type: 'server'; msg: ServerMessage }
  | { type: 'conn'; conn: Conn }
  | { type: 'draft'; text: string }
  | { type: 'pending'; id: string; text: string }
  | { type: 'failed'; id: string }
  | { type: 'acked'; id: string; intent: number }
  | { type: 'cleared' }

/** Insert keeping `order` sorted by when the thing happened.
 *
 *  Not by id: transcription lags by seconds, so what you said arrives after
 *  the strokes you wrote while waiting for it. Sorting by arrival would put
 *  them in an order the room never happened in. */
function place(state: State, row: Row): State {
  const rows = new Map(state.rows)
  const existing = rows.get(row.id)
  rows.set(row.id, row)
  if (existing) return { ...state, rows }

  const order = [...state.order]
  let at = order.length
  while (at > 0 && (rows.get(order[at - 1])?.t_ms ?? 0) > row.t_ms) at--
  order.splice(at, 0, row.id)
  return { ...state, rows, order }
}

function settle(state: State, event: DiaryEvent): State {
  // A note we sent optimistically comes back as a real row. Replace it in
  // place rather than appending, so nothing jumps under the reader's thumb.
  //
  // By intent id where there is one -- a send and the reply it causes share
  // no text at all, so matching on the words could never have worked for
  // anything but a plain note.
  const intent = typeof event.meta.intent === 'number' ? event.meta.intent : null
  const pending = state.order.find((id) => {
    const row = state.rows.get(id)
    if (row?.kind !== 'pending') return false
    if (intent !== null && row.intent === intent) return true
    return event.kind === 'note' && row.text === event.text
  })
  let next = state
  if (pending) {
    const rows = new Map(next.rows)
    rows.delete(pending)
    next = { ...next, rows, order: next.order.filter((id) => id !== pending) }
  }
  return place(next, {
    kind: 'event',
    id: `e${event.id}`,
    t_ms: event.t_ms,
    event,
  })
}

export function reduce(state: State, action: Action): State {
  switch (action.type) {
    case 'conn':
      return { ...state, conn: action.conn }
    case 'draft':
      return { ...state, draft: action.text }
    case 'pending':
      return place(state, {
        kind: 'pending',
        id: action.id,
        t_ms: nowMs(state),
        text: action.text,
      })
    case 'acked': {
      const row = state.rows.get(action.id)
      if (row?.kind !== 'pending') return state
      return place(state, { ...row, intent: action.intent })
    }
    case 'failed': {
      const row = state.rows.get(action.id)
      if (row?.kind !== 'pending') return state
      return place(state, { ...row, failed: true })
    }
    case 'cleared':
      // Optimistic, and the only reason the button feels like a button: the
      // loop has to take the ink off the page before it can say it cleared
      // anything, and that is seconds of eraser. The server's own row wipes
      // the same state again when it lands.
      return { ...state, rows: new Map(), order: [] }
    case 'server': {
      const msg = action.msg
      if (msg.type === 'hello.ok') {
        return {
          ...state,
          conn: 'open',
          session: msg.session,
          startedMs: msg.started_ms,
          serverNowMs: msg.now_ms,
          greetedAt: performance.now(),
          listening: msg.listening,
          live: msg.live ?? false,
          diary: msg.diary ?? state.diary,
        }
      }
      if (msg.type === 'diary') {
        const { type: _ignored, ...diary } = msg
        return { ...state, diary }
      }
      if (msg.type === 'hearing') {
        return { ...state, hearing: msg.on }
      }
      if (msg.type === 'pending') {
        return {
          ...state,
          reading: msg.on
            ? [...state.reading, msg.clip]
            : state.reading.filter((clip) => clip !== msg.clip),
        }
      }
      if (msg.type === 'event') {
        const { type: _ignored, ...event } = msg
        const row = event as DiaryEvent
        const seq = Math.max(state.seq, row.id)
        // The rows behind this one were deleted from the store, so the page
        // drops them rather than showing a past nothing else can see. The
        // marker itself is not placed: what is left is an empty timeline.
        if (row.kind === 'tool' && row.meta.doing === 'cleared')
          return { ...state, rows: new Map(), order: [], seq }
        return { ...settle(state, row), seq }
      }
      return state
    }
    default:
      return state
  }
}

/** The session clock, as this page best knows it: what the server said when
 *  it greeted us, plus how long ago that was by a clock that cannot step. */
export function nowMs(state: State): number {
  if (state.serverNowMs === null || state.greetedAt === null) {
    return state.startedMs ? Date.now() - state.startedMs : 0
  }
  return state.serverNowMs + Math.round(performance.now() - state.greetedAt)
}

export function rowsInOrder(state: State): Row[] {
  return state.order.map((id) => state.rows.get(id)!).filter(Boolean)
}
