import { useState } from 'react'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
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

/** `/api/captures/<name>` serves one file out of `var/captures`, so only the
 *  name goes in the url. The store spells `event.path` relative to `var/`,
 *  but rows written before that was true spell it from the checkout root, so
 *  take the last segment rather than trusting one prefix. */
function captureSrc(path: string) {
  return `/api/captures/${encodeURIComponent(path.split('/').pop() ?? '')}`
}

/** The capture is opaque on purpose -- it is also what the model is shown,
 *  and a transparent png composited onto black would hand it a blank page.
 *  So the paper is dropped here instead, in the browser: multiply drops a
 *  white background against a light theme, and inverting first turns the ink
 *  white so screen can drop the black against a dark one. Either way what is
 *  left is the ink, sitting on the card like any other row. */
const INK = 'mix-blend-multiply dark:invert dark:mix-blend-screen'

/** The page is the whole point of a strokes row, so it is shown as large as
 *  the card allows and opens full size on a tap. A capture that has been
 *  pruned off disk says so rather than leaving a broken image behind. */
function Capture({
  path,
  alt,
  className,
}: {
  path: string
  alt: string
  className?: string
}) {
  const [missing, setMissing] = useState(false)
  const src = captureSrc(path)
  if (missing)
    return (
      <p className="mt-1 text-xs text-muted-foreground">
        that page is no longer on disk
      </p>
    )
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button type="button" className="mt-1 block w-full cursor-zoom-in">
          <img
            src={src}
            alt={alt}
            onError={() => setMissing(true)}
            className={`w-full object-contain ${INK} ${className ?? ''}`}
            loading="lazy"
          />
        </button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-3xl">
        <DialogTitle className="text-xs font-normal uppercase tracking-wide text-muted-foreground">
          {alt}
        </DialogTitle>
        <img
          src={src}
          alt={alt}
          className={`max-h-[75vh] w-full object-contain ${INK}`}
        />
      </DialogContent>
    </Dialog>
  )
}

/** Who a row belongs to decides which edge it sits against: what you said or
 *  wrote hangs off the right, what the diary answered off the left, the way
 *  any chat reads. `full` is for rows that belong to neither. */
function Row({
  children,
  at,
  label,
  side = 'full',
  className = '',
}: {
  children: React.ReactNode
  at: number
  label: string
  side?: 'mine' | 'theirs' | 'full'
  className?: string
}) {
  const card = (
    <Card className={`gap-2 px-4 py-3 ${className}`}>
      <div className="flex items-baseline justify-between gap-3 text-xs text-muted-foreground">
        <span className="uppercase tracking-wide">{label}</span>
        <time className="tabular-nums">{clock(at)}</time>
      </div>
      {children}
    </Card>
  )
  if (side === 'full') return card
  return (
    <div className={`flex ${side === 'mine' ? 'justify-end' : 'justify-start'}`}>
      {card}
    </div>
  )
}

export function PenStrokeRow({ event }: { event: DiaryEvent }) {
  const strokes = Number(event.meta.strokes ?? 0)
  const path = event.path
  return (
    <Row at={event.wall_ms} label="written" side="mine" className="max-w-[85%]">
      <p className="text-sm text-muted-foreground">
        {strokes} stroke{strokes === 1 ? '' : 's'}
        {event.dur_ms > 0 ? ` over ${(event.dur_ms / 1000).toFixed(1)}s` : ''}
      </p>
      {path && <Capture path={path} alt="what was written" className="max-h-80" />}
    </Row>
  )
}

export function ShotRow({ event }: { event: DiaryEvent }) {
  const path = event.path
  return (
    <Row at={event.wall_ms} label="the screen">
      {path && <Capture path={path} alt="the tablet's screen" className="max-h-80" />}
    </Row>
  )
}

export function VoiceSegmentRow({ event }: { event: DiaryEvent }) {
  return (
    <Row at={event.wall_ms} label="said" side="mine" className="max-w-[85%]">
      <p className="text-sm leading-relaxed">{event.text}</p>
    </Row>
  )
}

export function NoteRow({ event }: { event: DiaryEvent }) {
  // A note the diary wrote to itself, rather than one you typed.
  const remembered = event.meta.remember === true
  return (
    <Row
      at={event.wall_ms}
      label={remembered ? 'kept' : 'typed'}
      side="mine"
      className="max-w-[85%]"
    >
      <p className="text-sm leading-relaxed">{event.text}</p>
    </Row>
  )
}

export function ReplyRow({ event }: { event: DiaryEvent }) {
  return (
    <Row
      at={event.wall_ms}
      label="the diary"
      side="theirs"
      className="max-w-[85%] border-foreground/15 bg-muted/40"
    >
      <p className="text-sm leading-relaxed">{emphasise(event.text ?? '')}</p>
    </Row>
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
    <div className="flex justify-end">
      <Card className="max-w-[85%] gap-2 px-4 py-3 opacity-70">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">
          {failed ? 'not delivered' : 'sending'}
        </div>
        <p className="text-sm leading-relaxed">{text}</p>
        {!failed && <Skeleton className="h-3 w-24" />}
      </Card>
    </div>
  )
}
