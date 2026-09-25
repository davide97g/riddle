import { useState } from 'react'
import { InkDots, NibStroke, StatusLine } from '@/components/Status'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
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
export const INK = 'mix-blend-multiply dark:invert dark:mix-blend-screen'

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
  const [inked, setInked] = useState(false)
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
        <button
          type="button"
          className="mt-1 block w-full cursor-zoom-in transition-transform duration-150 ease-out active:scale-[0.99]"
        >
          <img
            src={src}
            alt={alt}
            onError={() => setMissing(true)}
            onLoad={() => setInked(true)}
            // A capture arrives after its row does. Fading it in over the
            // space already reserved for it means the row does not jump.
            className={`w-full object-contain transition-opacity duration-300 ease-out ${
              inked ? 'opacity-100' : 'opacity-0'
            } ${INK} ${className ?? ''}`}
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
    <Card className={`row-in gap-2 px-4 py-3 ${className}`}>
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

/** Which way the disclosure points. Not a motif -- those three say what the
 *  diary is doing, and this says what you may open. */
function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 12 12"
      aria-hidden
      className={`h-3 w-3 transition-transform duration-150 ${open ? 'rotate-90' : ''}`}
    >
      <path
        d="M4 2.5 8 6l-4 3.5"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** The whole page, photographed before the eraser ran, and folded away.
 *
 *  This row lands on every turn, whether or not the model went and looked,
 *  and it is a picture of the entire page -- so left open it repeats your
 *  own handwriting down the timeline and drowns the conversation it exists
 *  to be context for. Collapsed it reads as one line among the tool rows,
 *  which is what it is: something the diary was offered. Opening it shows
 *  the photograph, and the photograph still opens full size from there. */
export function ShotRow({ event }: { event: DiaryEvent }) {
  const [open, setOpen] = useState(false)
  const path = event.path
  if (!path) return null
  return (
    <div className="row-in flex flex-col gap-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-1 text-left text-xs text-muted-foreground transition-colors hover:text-foreground"
      >
        <span className="flex w-[30px] shrink-0 justify-center">
          <Chevron open={open} />
        </span>
        <span className="min-w-0">
          the whole page, photographed at {clock(event.wall_ms)}
        </span>
      </button>
      {open && (
        <Capture path={path} alt="the tablet's screen" className="max-h-80" />
      )}
    </div>
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

/** `fresh` is set only for the newest row. One reply writing itself on is
 *  worth watching; a screen of resumed history all wiping in at once is
 *  not. */
export function ReplyRow({ event, fresh }: { event: DiaryEvent; fresh?: boolean }) {
  return (
    <Row
      at={event.wall_ms}
      label="the diary"
      side="theirs"
      className="max-w-[85%] border-foreground/15 bg-muted/40"
    >
      <p className={`text-sm leading-relaxed ${fresh ? 'ink-reveal' : ''}`}>
        {emphasise(event.text ?? '')}
      </p>
    </Row>
  )
}

/** Which of the three motifs a `tool` row gets, from the verb the loop put in
 *  `meta.doing`. Matched on a stem rather than a list, because the loop is
 *  free to invent a verb and an unknown one should still look like work
 *  rather than like nothing: thinking is the fallback, and thinking is what
 *  anything unrecognised is doing. */
function motifFor(doing: string, still: boolean) {
  if (/eras|rubb|clear|wip/.test(doing)) return <NibStroke back still={still} />
  if (/writ|draw|ink|sketch|answer/.test(doing)) return <NibStroke still={still} />
  return <InkDots still={still} />
}

/** What the diary is doing, or was.
 *
 *  Only the newest row is still happening: anything with a row under it has
 *  been overtaken by whatever came next, however it ended. So the motion --
 *  and the announcement -- belong to the last row alone, and the rest of the
 *  timeline holds still. */
export function ToolRow({ event, live = false }: { event: DiaryEvent; live?: boolean }) {
  const doing = String(event.meta.doing ?? event.text ?? 'thinking')
  return (
    <StatusLine motif={motifFor(doing, !live)} live={live}>
      the diary is {doing}
    </StatusLine>
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
      <Card
        // Keyed on the outcome so a send that fails re-enters and nudges
        // once, instead of quietly relabelling itself where you are not
        // looking. The row stays faded until the server's own copy replaces
        // it: this one is a promise, not a record.
        key={failed ? 'failed' : 'sending'}
        className={`max-w-[85%] gap-2 px-4 py-3 transition-opacity duration-200 ${
          failed ? 'nudge border-destructive/40 opacity-90' : 'row-in opacity-70'
        }`}
      >
        <div
          className={`text-xs uppercase tracking-wide ${
            failed ? 'text-destructive' : 'text-muted-foreground'
          }`}
        >
          {failed ? 'not delivered' : 'sending'}
        </div>
        <p className="text-sm leading-relaxed">{text}</p>
        {!failed && <span className="ink-sweep h-1 w-24 text-muted-foreground" />}
      </Card>
    </div>
  )
}
