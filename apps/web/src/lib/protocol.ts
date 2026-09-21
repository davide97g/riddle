// The wire, written out by hand rather than generated. There are a dozen
// messages and one backend; a codegen step would be more moving parts than
// the thing it describes.

export type EventKind =
  | 'strokes'
  | 'speech'
  | 'shot'
  | 'reply'
  | 'note'
  | 'tool'
  | 'error'

export type DiaryEvent = {
  id: number
  kind: EventKind
  /** ms since the session started. This is what the timeline sorts by. */
  t_ms: number
  dur_ms: number
  /** unix epoch ms, for saying what time of day something happened */
  wall_ms: number
  turn: number | null
  text: string | null
  path: string | null
  meta: Record<string, unknown>
}

/** Whether the half that owns the pen is running. Without it the page
 *  promises an answer that nothing is there to give. */
export type DiaryPresence = { present: boolean; ago_ms: number | null }

export type ServerMessage =
  | ({ type: 'event' } & DiaryEvent)
  | {
      type: 'hello.ok'
      session: number
      started_ms: number
      now_ms: number
      listening: boolean
      diary: DiaryPresence
    }
  /** a send was recorded, and this is its id. the reply carries the same id
   *  in meta.intent, which is how an optimistic row settles */
  | { type: 'intent.ok'; id: number; at_ms: number }
  | { type: 'pong'; t: number }
  /** the gate opened or closed: somebody is speaking, or has stopped */
  | { type: 'hearing'; on: boolean }
  /** a sentence is being read. there is no partial text to show, because the
   *  model takes a file and reloads itself on every run */
  | { type: 'pending'; clip: string; on: boolean }
  | { type: 'error'; message: string }

export type ClientMessage =
  | { type: 'hello'; since: number; limit?: number }
  | { type: 'ping'; t: number }
  | { type: 'note'; text: string }
  | { type: 'send'; at_ms: number; draft: string }

/** A row on screen: either something the server told us, or something we have
 *  said but not yet seen come back. */
export type Row =
  | { kind: 'event'; id: string; t_ms: number; event: DiaryEvent }
  | {
      kind: 'pending'
      id: string
      t_ms: number
      text: string
      failed?: boolean
      /** set once the server has acknowledged the send */
      intent?: number
    }
