import { Camera, Copy, Download, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { INK } from '@/components/rows/Rows'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { blobOf, copyPng, fileName } from '@/hooks/useSnapshots'
import type { Snapshot } from '@/hooks/useSnapshots'

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
      Snapshot
    </Button>
  )
}

function Actions({ snap, remove }: { snap: Snapshot; remove: (id: string) => void }) {
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
        onClick={() => remove(snap.id)}
        aria-label="Delete this snapshot"
        title="Delete this snapshot"
      >
        <Trash2 className="size-4" />
      </Button>
    </>
  )
}

/** One kept frame: a thumbnail that opens full size, and what can be done
 *  with it. What is downloaded or copied is the frame as the tablet sent
 *  it -- white paper, black ink -- whatever the theme did to the preview. */
function Kept({ snap, remove }: { snap: Snapshot; remove: (id: string) => void }) {
  const label = clock(snap.at)
  return (
    <li className="row-in flex w-20 shrink-0 flex-col gap-1 lg:w-full">
      <Dialog>
        <DialogTrigger asChild>
          <button
            type="button"
            // The background is the backdrop the ink blends against: the
            // row's entrance animation isolates it from the page's own.
            className="block cursor-zoom-in rounded-sm border bg-background transition-transform duration-150 ease-out active:scale-[0.98]"
            aria-label={`Open the snapshot from ${label}`}
          >
            <img src={snap.png} alt="" className={`aspect-[1404/1872] w-full ${INK}`} />
          </button>
        </DialogTrigger>
        <DialogContent className="sm:max-w-3xl">
          <DialogTitle className="text-xs font-normal uppercase tracking-wide text-muted-foreground">
            {label}
          </DialogTitle>
          <img
            src={snap.png}
            alt={`The page on the tablet at ${label}`}
            className={`max-h-[70vh] w-full object-contain ${INK}`}
          />
          <DialogFooter className="flex-row justify-end gap-1">
            <Actions snap={snap} remove={remove} />
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <time className="truncate text-xs tabular-nums text-muted-foreground" title={label}>
        {time(snap.at)}
      </time>
      {/* On a phone there is no room for three buttons under a thumbnail;
          the same three are in the preview a tap away. */}
      <div className="-ml-2 hidden items-center lg:flex">
        <Actions snap={snap} remove={remove} />
      </div>
    </li>
  )
}

/** The last ten snapshots, newest first. Two columns beside the page where
 *  there is room, a strip under it on a phone, and on a phone nothing at
 *  all until there is something on it. */
export function SnapshotShelf({
  snaps,
  kept,
  remove,
}: {
  snaps: Snapshot[]
  kept: boolean
  remove: (id: string) => void
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
          Take one and it lands here, and on your clipboard.
        </p>
      ) : (
        <ul className="flex gap-3 overflow-x-auto pb-1 lg:grid lg:grid-cols-2 lg:overflow-x-visible">
          {snaps.map((snap) => (
            <Kept key={snap.id} snap={snap} remove={remove} />
          ))}
        </ul>
      )}
    </aside>
  )
}
