import { Camera, Copy, Download, Sparkles, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { INK } from '@/components/rows/Rows'
import { InkDots, StatusLine } from '@/components/Status'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogTitle } from '@/components/ui/dialog'
import { blobOf, copyPng, fileName } from '@/hooks/useSnapshots'
import type { Reading, Snapshot } from '@/hooks/useSnapshots'

function clock(at: number) {
  return new Date(at).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function time(at: number) {
  return new Date(at).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function copy(snap: Snapshot) {
  copyPng(blobOf(snap)).then(
    () => toast.success('Copied to the clipboard'),
    (err: Error) => toast.error('Could not copy it', { description: err.message }),
  )
}

/** Everything one shelf needs to act on a snapshot. */
export type ShelfActions = {
  remove: (id: string) => void
  understand: (snap: Snapshot) => void
  reading: Record<string, Reading>
  /** which snapshot's preview is open; lifted so a snapshot taken to be
   *  understood can open itself */
  open: string | null
  setOpen: (id: string | null) => void
}

/** Take the frame on screen: onto the clipboard, and onto the shelf.
 *
 *  Both at once rather than a choice, because the one you did not pick is
 *  the one you wanted. The copy is started before anything is awaited, or
 *  Safari decides the click is over and refuses it. */
export function SnapButton({
  frame,
  take,
}: {
  frame: Blob | null
  take: (png: Blob) => Promise<Snapshot>
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      disabled={!frame}
      title={frame ? 'Copy this page and keep it below' : 'Waiting for the first frame.'}
      onClick={() => {
        if (!frame) return
        const copied = copyPng(frame).then(
          () => true,
          () => false,
        )
        Promise.all([copied, take(frame)]).then(
          ([ok]) =>
            ok
              ? toast.success('Snapshot copied', { description: 'Kept on the shelf too.' })
              : toast('Snapshot kept', {
                  description: 'This browser would not put it on the clipboard.',
                }),
          (err: Error) => toast.error('Could not take it', { description: err.message }),
        )
      }}
    >
      <Camera className="size-4" />
      <span className="max-sm:sr-only">Snapshot</span>
    </Button>
  )
}

/** Snapshot the frame on screen and ask what is on it, in one press.
 *
 *  It is a snapshot first so the reading has somewhere to live: it is kept
 *  with the frame it describes, on the shelf, and the preview opens so the
 *  answer arrives where you are looking. The clipboard is left alone --
 *  this press asked a question, not for a copy. */
export function UnderstandButton({
  frame,
  take,
  understand,
  setOpen,
}: {
  frame: Blob | null
  take: (png: Blob) => Promise<Snapshot>
  understand: (snap: Snapshot) => void
  setOpen: (id: string | null) => void
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      disabled={!frame}
      title={frame ? 'Snapshot this page and ask what is on it' : 'Waiting for the first frame.'}
      onClick={() => {
        if (!frame) return
        take(frame).then(
          (snap) => {
            setOpen(snap.id)
            understand(snap)
          },
          (err: Error) => toast.error('Could not take it', { description: err.message }),
        )
      }}
    >
      <Sparkles className="size-4" />
      <span className="max-sm:sr-only">Understand</span>
    </Button>
  )
}

function Actions({ snap, act }: { snap: Snapshot; act: ShelfActions }) {
  const busy = act.reading[snap.id]?.state === 'reading'
  return (
    <>
      <Button asChild size="icon-sm" variant="ghost">
        <a href={snap.png} download={fileName(snap.at)} aria-label="Download as png" title="Download as png">
          <Download className="size-4" />
        </a>
      </Button>
      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        onClick={() => copy(snap)}
        aria-label="Copy to the clipboard"
        title="Copy to the clipboard"
      >
        <Copy className="size-4" />
      </Button>
      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        disabled={busy}
        onClick={() => {
          act.setOpen(snap.id)
          act.understand(snap)
        }}
        aria-label={snap.understood ? 'Understand it again' : 'Understand this page'}
        title={snap.understood ? 'Ask again what is on it' : 'Ask what is on this page'}
      >
        <Sparkles className="size-4" />
      </Button>
      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        onClick={() => act.remove(snap.id)}
        aria-label="Delete this snapshot"
        title="Delete this snapshot"
      >
        <Trash2 className="size-4" />
      </Button>
    </>
  )
}

/** What the model made of a page, laid out rather than printed.
 *
 *  An old reading stays on screen, dimmed, while a new one is fetched: the
 *  page it describes has not changed, and a blank panel for three seconds
 *  would say it had. */
function Understood({ snap, act }: { snap: Snapshot; act: ShelfActions }) {
  const status = act.reading[snap.id]
  const read = snap.understood

  if (!read && !status)
    return (
      <div className="flex h-full flex-col items-start justify-center gap-3 py-6">
        <p className="text-sm text-muted-foreground">
          Ask what is on this page: the writing as text, and what the drawing
          means. The snapshot is sent to OpenAI to be read.
        </p>
        <Button type="button" size="sm" onClick={() => act.understand(snap)}>
          <Sparkles className="size-4" />
          Understand
        </Button>
      </div>
    )

  return (
    <div className="flex flex-col gap-4" aria-busy={status?.state === 'reading'}>
      {status?.state === 'reading' && (
        <StatusLine motif={<InkDots />}>reading the page</StatusLine>
      )}
      {status?.state === 'failed' && (
        <div className="flex flex-col items-start gap-2">
          <p className="text-sm text-destructive">Could not read it: {status.message}</p>
          <Button type="button" size="sm" variant="outline" onClick={() => act.understand(snap)}>
            Try again
          </Button>
        </div>
      )}
      {read && (
        <div
          className={`row-in flex flex-col gap-4 transition-opacity ${
            status?.state === 'reading' ? 'opacity-40' : 'opacity-100'
          }`}
        >
          <div className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-base font-medium">{read.title}</h3>
              <Badge variant="outline" className="font-normal">
                {read.kind}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              read by {read.model} in {(read.took_ms / 1000).toFixed(1)}s
            </p>
          </div>
          <p className="text-sm leading-relaxed">{read.summary}</p>
          {read.points.length > 0 && (
            <ul className="flex list-disc flex-col gap-1.5 pl-5 text-sm leading-relaxed">
              {read.points.map((point, i) => (
                <li key={i}>{point}</li>
              ))}
            </ul>
          )}
          {read.transcript.trim() && (
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between">
                <span className="text-xs uppercase tracking-wide text-muted-foreground">
                  Transcript
                </span>
                <Button
                  type="button"
                  size="icon-sm"
                  variant="ghost"
                  aria-label="Copy the transcript"
                  title="Copy the transcript"
                  onClick={() =>
                    navigator.clipboard.writeText(read.transcript).then(
                      () => toast.success('Transcript copied'),
                      (err: Error) => toast.error('Could not copy it', { description: err.message }),
                    )
                  }
                >
                  <Copy className="size-4" />
                </Button>
              </div>
              <pre className="rounded-md bg-muted px-3 py-2 font-mono text-xs leading-relaxed whitespace-pre-wrap">
                {read.transcript}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** One kept frame: a thumbnail that opens full size beside what the model
 *  made of it. What is downloaded or copied is the frame as the tablet sent
 *  it -- white paper, black ink -- whatever the theme did to the preview. */
function Kept({ snap, act }: { snap: Snapshot; act: ShelfActions }) {
  const label = clock(snap.at)
  const reading = act.reading[snap.id]?.state === 'reading'
  return (
    <li className="row-in flex w-20 shrink-0 flex-col gap-1 lg:w-full">
      <button
        type="button"
        onClick={() => act.setOpen(snap.id)}
        // The background is the backdrop the ink blends against: the row's
        // entrance animation isolates it from the page's own.
        className="relative block cursor-zoom-in rounded-sm border bg-background transition-transform duration-150 ease-out active:scale-[0.98]"
        aria-label={`Open the snapshot from ${label}`}
      >
        <img src={snap.png} alt="" className={`aspect-[1404/1872] w-full ${INK}`} />
        {(reading || snap.understood) && (
          <span
            className="absolute top-1 right-1 flex items-center rounded-full bg-background/90 p-1 text-muted-foreground"
            title={reading ? 'Being read' : 'Understood'}
          >
            {reading ? <InkDots className="h-2 w-[18px]" /> : <Sparkles className="size-3" />}
          </span>
        )}
      </button>
      <time className="truncate text-xs tabular-nums text-muted-foreground" title={label}>
        {time(snap.at)}
      </time>
      {/* On a phone there is no room for the buttons under a thumbnail; the
          same ones are in the preview a tap away. */}
      <div className="-ml-2 hidden flex-wrap items-center lg:flex">
        <Actions snap={snap} act={act} />
      </div>
      <Dialog open={act.open === snap.id} onOpenChange={(open) => act.setOpen(open ? snap.id : null)}>
        <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-4xl">
          <DialogTitle className="text-xs font-normal uppercase tracking-wide text-muted-foreground">
            {label}
          </DialogTitle>
          <div className="grid gap-4 md:grid-cols-2">
            <img
              src={snap.png}
              alt={`The page on the tablet at ${label}`}
              className={`max-h-[45dvh] w-full rounded-sm border bg-background object-contain md:max-h-[70vh] ${INK}`}
            />
            <div className="min-w-0 md:max-h-[70vh] md:overflow-y-auto md:pr-1">
              <Understood snap={snap} act={act} />
            </div>
          </div>
          <DialogFooter className="flex-row justify-end gap-1">
            <Actions snap={snap} act={act} />
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </li>
  )
}

/** The last ten snapshots, newest first. Two columns beside the page where
 *  there is room, a strip under it on a phone, and on a phone nothing at
 *  all until there is something on it. */
export function SnapshotShelf({
  snaps,
  kept,
  act,
}: {
  snaps: Snapshot[]
  kept: boolean
  act: ShelfActions
}) {
  return (
    <aside
      className={`shrink-0 border-t px-4 py-3 lg:w-64 lg:overflow-y-auto lg:border-t-0 lg:border-l ${
        snaps.length ? '' : 'hidden lg:block'
      }`}
    >
      <h2 className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
        Snapshots {snaps.length > 0 && <span className="tabular-nums">· {snaps.length}/10</span>}
      </h2>
      {!kept && (
        <p className="mb-2 text-xs text-destructive">
          This browser's storage is full: the oldest will not survive a reload.
        </p>
      )}
      {snaps.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Take one and it lands here, and on your clipboard. Understand one to
          have it read.
        </p>
      ) : (
        <ul className="flex gap-3 overflow-x-auto pb-1 lg:grid lg:grid-cols-2 lg:overflow-x-visible">
          {snaps.map((snap) => (
            <Kept key={snap.id} snap={snap} act={act} />
          ))}
        </ul>
      )}
    </aside>
  )
}
