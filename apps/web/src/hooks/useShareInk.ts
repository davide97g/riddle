import { useCallback, useEffect, useRef, useState } from 'react'
import { useRiddleSocket } from '@/hooks/useRiddleSocket'
import { crosses } from '@/lib/share'
import type { Conn, Action } from '@/state/reducer'
import type { DiaryPresence, InkMeta } from '@/lib/protocol'

/** How often the page says it is still sharing. The loop counts a share as
 *  gone fifteen seconds after the last beat, so a page closed without a word
 *  lets go of the diary on its own. */
const BEAT_MS = 5000
/** The loop's own `ERASE_RADIUS`, so a pass rubs out here what it did there. */
const ERASE_RADIUS = 28

export type InkStroke = { id: number; points: [number, number][] }

/** The pen on the tablet, stroke by stroke, while this page shares a screen.
 *
 *  Its own events socket and no provider: the timeline's rows are nothing to
 *  this page, and holding five hundred of them to draw a few strokes would be
 *  the whole diary loaded to show a sketch. The reducer's `event` handling is
 *  not needed either -- only `ink`, and only strokes written after `mark()`,
 *  which is the moment a frame went to the tablet. Everything before that
 *  was written on some other page. */
export function useShareInk(on: boolean) {
  const [conn, setConn] = useState<Conn>('connecting')
  const [diary, setDiary] = useState<DiaryPresence | null>(null)
  const [strokes, setStrokes] = useState<InkStroke[]>([])
  const seen = useRef(0)
  // null until a frame has been sent: nothing is drawn over a screen the
  // tablet was never shown.
  const since = useRef<number | null>(null)

  const dispatch = useCallback((action: Action) => {
    if (action.type === 'conn') return setConn(action.conn)
    if (action.type !== 'server') return
    const msg = action.msg
    if (msg.type === 'hello.ok') {
      setConn('open')
      setDiary(msg.diary ?? null)
      return
    }
    if (msg.type === 'diary') {
      const { type: _ignored, ...presence } = msg
      return setDiary(presence)
    }
    if (msg.type !== 'event') return
    seen.current = Math.max(seen.current, msg.id)
    if (msg.kind !== 'ink' || since.current === null || msg.id <= since.current) return
    const ink = msg.meta as InkMeta
    if (!Array.isArray(ink.points) || ink.points.length === 0) return
    if (ink.tool === 'rubber') {
      setStrokes((all) => all.filter((s) => !crosses(s.points, ink.points, ERASE_RADIUS)))
      return
    }
    setStrokes((all) => (all.some((s) => s.id === msg.id) ? all : [...all, { id: msg.id, points: ink.points }]))
  }, [])

  const say = useRiddleSocket(dispatch)

  // The beat. Sent at once and then every few seconds rather than once:
  // a socket that dropped and came back would otherwise have said it once, to
  // nobody. Said again on every reconnect for the same reason.
  useEffect(() => {
    if (!on || conn !== 'open') return
    say({ type: 'share', on: true })
    const timer = window.setInterval(() => say({ type: 'share', on: true }), BEAT_MS)
    return () => {
      window.clearInterval(timer)
      say({ type: 'share', on: false })
    }
  }, [on, conn, say])

  /** A new frame went to the tablet: what was drawn over the last one goes. */
  const mark = useCallback(() => {
    since.current = seen.current
    setStrokes([])
  }, [])

  const clear = useCallback(() => setStrokes([]), [])

  return { conn, diary, strokes, mark, clear }
}
