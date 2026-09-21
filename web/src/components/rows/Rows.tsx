import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import type { DiaryEvent } from '@/lib/protocol'

function clock(wall: number) {
  return new Date(wall).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/** `*asterisks*` mean the same here as they do on the page: style.py gives
 *  them a heavier hand, so the screen and the tablet agree about what the
 *  diary leaned on. */
function emphasise(text: string) {
  return text.split(/(\*[^*]+\*)/g).map((part, i) =>
    part.startsWith('*') && part.endsWith('*') && part.length > 2 ? (
      <em key={i} className="font-medium not-italic text-foreground">
        {part.slice(1, -1)}
      </em>
    ) : (
      <span key={i}>{part}</span>
    ),
  )
}

function Row({
  children,
  at,
  label,
  className = '',
}: {
  children: React.ReactNode
  at: number
  label: string
  className?: string
}) {
  return (
    <Card className={`gap-2 px-4 py-3 ${className}`}>
      <div className="flex items-baseline justify-between gap-3 text-xs text-muted-foreground">
        <span className="uppercase tracking-wide">{label}</span>
        <time className="tabular-nums">{clock(at)}</time>
      </div>
      {children}
    </Card>
  )
}

export function PenStrokeRow({ event }: { event: DiaryEvent }) {
  const strokes = Number(event.meta.strokes ?? 0)
  const path = typeof event.meta.path === 'string' ? event.meta.path : null
  return (
    <Row at={event.wall_ms} label="written">
      <p className="text-sm text-muted-foreground">
        {strokes} stroke{strokes === 1 ? '' : 's'}
        {event.dur_ms > 0 ? ` over ${(event.dur_ms / 1000).toFixed(1)}s` : ''}
      </p>
      {path && (
        <img
          src={`/api/captures/${path.replace(/^captures\//, '')}`}
          alt="what was written"
          className="mt-1 max-h-48 w-full rounded-md border object-contain"
          loading="lazy"
        />
      )}
    </Row>
  )
}

export function VoiceSegmentRow({ event }: { event: DiaryEvent }) {
  return (
    <Row at={event.wall_ms} label="said">
      <p className="text-sm leading-relaxed">{event.text}</p>
    </Row>
  )
}

export function NoteRow({ event }: { event: DiaryEvent }) {
  return (
    <Row at={event.wall_ms} label="typed">
      <p className="text-sm leading-relaxed">{event.text}</p>
    </Row>
  )
}

export function ReplyRow({ event }: { event: DiaryEvent }) {
  return (
    <div className="flex justify-end">
      <Row
        at={event.wall_ms}
        label="the diary"
        className="max-w-[85%] border-foreground/15 bg-muted/40"
      >
        <p className="text-sm leading-relaxed">{emphasise(event.text ?? '')}</p>
      </Row>
    </div>
  )
}

export function ToolRow({ event }: { event: DiaryEvent }) {
  return (
    <p className="px-1 text-xs text-muted-foreground">
      the diary is {String(event.meta.doing ?? event.text ?? 'thinking')}
    </p>
  )
}

export function ErrorRow({ event }: { event: DiaryEvent }) {
  return (
    <Row at={event.wall_ms} label="went wrong" className="border-destructive/40">
      <p className="text-sm text-destructive">{event.text}</p>
    </Row>
  )
}

export function PendingRow({ text, failed }: { text: string; failed?: boolean }) {
  return (
    <Card className="gap-2 px-4 py-3 opacity-70">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        {failed ? 'not delivered' : 'sending'}
      </div>
      <p className="text-sm leading-relaxed">{text}</p>
      {!failed && <Skeleton className="h-3 w-24" />}
    </Card>
  )
}
