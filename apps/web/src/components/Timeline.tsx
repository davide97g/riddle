import { useEffect, useRef, useState } from 'react'
import { InkWave, StatusLine } from '@/components/Status'
import { useDiary } from '@/state/RiddleProvider'
import { nowMs, rowsInOrder } from '@/state/reducer'
import {
  ErrorRow,
  NoteRow,
  PendingRow,
  PenStrokeRow,
  ReplyRow,
  ShotRow,
  ToolRow,
  VoiceSegmentRow,
} from '@/components/rows/Rows'

const NEAR_BOTTOM = 80

/** How long a `tool` row may go on claiming to be happening.
 *
 *  A motif that moves means "this is going on now", so it belongs to the
 *  newest row and to nothing above it. But being newest is not quite enough:
 *  nothing marks the end of a turn. The last thing the loop writes is
 *  `writing`, and after the pen stops there is no row to overtake it until
 *  somebody writes on the tablet again -- which may be an hour. So motion
 *  also expires. Long enough that a real reply is still being inked when it
 *  does, short enough that an idle page is still. */
const LIVE_MS = 60_000

export function Timeline() {
  const { state } = useDiary()
  const rows = rowsInOrder(state)
  const box = useRef<HTMLDivElement>(null)
  const stick = useRef(true)

  // Only the newest reply writes itself on. Two hundred rows of resumed
  // history all doing it at once is a page tearing itself apart, and the
  // last row is the one the eye is on anyway -- on a reload it marks where
  // the conversation had got to, which is worth a beat of motion.
  const newest = rows.at(-1)?.id

  // The newest row, if it is a `tool` row, is the only one whose motif may
  // move -- and only until it goes stale. Both clocks here are the session's,
  // never the browser's: `nowMs` is what the server said plus how long ago
  // it said it.
  const last = rows.at(-1)
  const going = last && last.kind !== 'pending' ? last.event : null
  const toolRow = going?.kind === 'tool' ? going : null
  const fresh = toolRow !== null && nowMs(state) - toolRow.t_ms < LIVE_MS
  // Nothing else will re-render the page while it sits idle, so the moment
  // the newest row goes stale has to be waited for on purpose.
  const [, retick] = useState(0)
  useEffect(() => {
    if (!toolRow || !fresh) return
    const left = LIVE_MS - (nowMs(state) - toolRow.t_ms)
    const timer = window.setTimeout(() => retick((n) => n + 1), Math.max(0, left))
    return () => window.clearTimeout(timer)
  }, [toolRow, fresh, state])

  useEffect(() => {
    const el = box.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [rows.length])

  return (
    <div
      ref={box}
      onScroll={(e) => {
        const el = e.currentTarget
        // Only follow if the reader is already at the bottom. Yanking the view
        // out from under someone reading back is worse than a missed row.
        stick.current =
          el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM
      }}
      className="flex-1 overflow-y-auto overscroll-contain px-4 py-4"
    >
      <div className="mx-auto flex max-w-2xl flex-col gap-3">
        {rows.length === 0 && (
          <div className="row-in flex flex-col items-center gap-3 py-16">
            <span className="splash-rule h-px w-24 bg-foreground/15" />
            <p className="text-center text-sm text-muted-foreground">
              Nothing yet. Write on the tablet, or say something.
            </p>
          </div>
        )}
        {rows.map((row) => {
          if (row.kind === 'pending')
            return <PendingRow key={row.id} text={row.text} failed={row.failed} />
          const event = row.event
          const now = row.id === newest
          switch (event.kind) {
            case 'strokes':
              return <PenStrokeRow key={row.id} event={event} />
            case 'shot':
              return <ShotRow key={row.id} event={event} />
            case 'speech':
              return <VoiceSegmentRow key={row.id} event={event} />
            case 'note':
              return <NoteRow key={row.id} event={event} />
            case 'reply':
              return <ReplyRow key={row.id} event={event} fresh={now} />
            case 'tool':
              return (
                <ToolRow key={row.id} event={event} live={row.id === newest && fresh} />
              )
            case 'error':
              return <ErrorRow key={row.id} event={event} />
            default:
              return null
          }
        })}
        {state.reading.map((clip) => (
          <StatusLine key={clip} motif={<InkWave />}>
            reading that back
          </StatusLine>
        ))}
        {state.hearing && state.reading.length === 0 && (
          <StatusLine motif={<InkWave />}>listening</StatusLine>
        )}
      </div>
    </div>
  )
}
