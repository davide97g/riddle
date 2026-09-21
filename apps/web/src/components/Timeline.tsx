import { useEffect, useRef } from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { useDiary } from '@/state/RiddleProvider'
import { rowsInOrder } from '@/state/reducer'
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

export function Timeline() {
  const { state } = useDiary()
  const rows = rowsInOrder(state)
  const box = useRef<HTMLDivElement>(null)
  const stick = useRef(true)

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
          <p className="py-16 text-center text-sm text-muted-foreground">
            Nothing yet. Write on the tablet, or say something.
          </p>
        )}
        {rows.map((row) => {
          if (row.kind === 'pending')
            return <PendingRow key={row.id} text={row.text} failed={row.failed} />
          const event = row.event
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
              return <ReplyRow key={row.id} event={event} />
            case 'tool':
              return <ToolRow key={row.id} event={event} />
            case 'error':
              return <ErrorRow key={row.id} event={event} />
            default:
              return null
          }
        })}
        {state.reading.map((clip) => (
          <div key={clip} className="flex flex-col gap-2 rounded-xl border px-4 py-3">
            <span className="text-xs uppercase tracking-wide text-muted-foreground">
              reading that back
            </span>
            <Skeleton className="h-4 w-3/4" />
          </div>
        ))}
        {state.hearing && state.reading.length === 0 && (
          <p className="px-1 text-xs text-muted-foreground">listening...</p>
        )}
      </div>
    </div>
  )
}
