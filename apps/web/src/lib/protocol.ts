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
export type DiaryPresence = {
  present: boolean
  ago_ms: number | null
  /** who runs that half on the server: a systemd user unit, or the server
   *  itself with a pidfile. A stop under systemd is a request to a
   *  supervisor, which is a weaker promise than a kill. */
  manager: 'systemd' | 'here'
  /** a start or stop asked from a page is still running */
  busy: boolean
}

export type ServerMessage =
  | ({ type: 'event' } & DiaryEvent)
  | {
      type: 'hello.ok'
      session: number
      started_ms: number
      now_ms: number
      listening: boolean
      /** whether this server will stream the tablet's screen on /ws/live,
       *  which is RIDDLE_ALLOW_SNAP and nothing else */
      live: boolean
      diary: DiaryPresence
    }
  /** a send was recorded, and this is its id. the reply carries the same id
   *  in meta.intent, which is how an optimistic row settles */
  | { type: 'intent.ok'; id: number; at_ms: number }
  /** the loop came, went, or is being started or stopped. Sent on every
   *  change, so a page that was open when it died learns without a reload */
  | ({ type: 'diary' } & DiaryPresence)
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
  /** the eraser: the diary rubs its ink off the page, forgets the
   *  conversation and deletes this session's rows. Nothing is acknowledged;
   *  the `tool` row with `meta.doing === 'cleared'` is what says it happened */
  | { type: 'clear' }
  /** bring the half that owns the pen up, or take it down. Not acknowledged:
   *  starting it is a process and then a heartbeat, and `diary` is what says
   *  it arrived. Only a failure comes back, as `error` */
  | { type: 'diary.start' }
  | { type: 'diary.stop' }

/** The text half of /ws/live; the binary half is one png per changed frame.
 *  `dialing` until the tablet answers, `on` while frames arrive, `lost` when
 *  the link dropped and the server is redialling by itself. */
export type LiveMessage = {
  type: 'live'
  state: 'dialing' | 'on' | 'lost'
  message?: string
}

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
