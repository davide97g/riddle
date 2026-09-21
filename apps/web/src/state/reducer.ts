import type { DiaryEvent, Row, ServerMessage } from '@/lib/protocol'

export type Conn = 'connecting' | 'open' | 'closed'

export type State = {
  /** highest event id applied, and what `hello` resumes from */
  seq: number
  rows: Map<string, Row>
  /** row ids, kept sorted by t_ms */
  order: string[]
  session: number | null
  startedMs: number | null
  listening: boolean
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
  listening: false,
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
  const pending = state.order.find((id) => {
    const row = state.rows.get(id)
    return (
      row?.kind === 'pending' &&
      event.kind === 'note' &&
      row.text === event.text
    )
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
        t_ms: state.startedMs ? Date.now() - state.startedMs : Date.now(),
        text: action.text,
      })
    case 'failed': {
      const row = state.rows.get(action.id)
      if (row?.kind !== 'pending') return state
      return place(state, { ...row, failed: true })
    }
    case 'server': {
      const msg = action.msg
      if (msg.type === 'hello.ok') {
        return {
          ...state,
          conn: 'open',
          session: msg.session,
          startedMs: msg.started_ms,
          listening: msg.listening,
        }
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
        return {
          ...settle(state, event as DiaryEvent),
          seq: Math.max(state.seq, event.id),
        }
      }
      return state
    }
    default:
      return state
  }
}

export function rowsInOrder(state: State): Row[] {
  return state.order.map((id) => state.rows.get(id)!).filter(Boolean)
}
