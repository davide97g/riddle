import { useEffect, useRef, useState } from 'react'
import { FileText, FileUp } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'

/** What the server will take, and the same ceiling it enforces. Checked here
 *  too so a 200MB video is refused now rather than after it has uploaded. */
const ACCEPT = 'application/pdf,.pdf,application/epub+zip,.epub,image/*'
const MAX_BYTES = 64 << 20

function title(file: File) {
  return file.name.replace(/\.[^.]+$/, '').trim() || 'Untitled'
}

function size(bytes: number) {
  if (bytes < 1 << 10) return `${bytes} B`
  if (bytes < 1 << 20) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1 << 20)).toFixed(1)} MB`
}

/** Put a file in the tablet's library, as a real document.
 *
 *  Not drawn: the pen can only trace a picture, and xochitl renders a pdf
 *  itself far better than a tracing of it -- sharp at every zoom, and a page
 *  you can write on. An image becomes a one-page pdf on the server; a pdf or
 *  an epub goes in as it is.
 *
 *  It asks first, every time, because the way in is a restart of xochitl:
 *  whatever is open on the tablet closes, and if the diary is halfway
 *  through a word, the word stops. The document then waits in the library;
 *  nothing here can open it.
 *
 *  A file can also be dropped anywhere on the page. */
export function SendToTablet() {
  const picker = useRef<HTMLInputElement>(null)
  // The file and its preview move together: the preview is an object url
  // made when the file is chosen and revoked when it is replaced or put
  // down. A pdf gets none -- rendering one in the browser would be a
  // library the size of this app, to show a thumbnail.
  const [chosen, setChosen] = useState<{ file: File; preview: string | null } | null>(null)
  const [name, setName] = useState('')
  const file = chosen?.file ?? null
  const preview = chosen?.preview ?? null
  const [sending, setSending] = useState(false)
  const [dragging, setDragging] = useState(false)

  const choose = (next: File | null | undefined) => {
    if (!next) return
    if (next.size > MAX_BYTES) {
      toast.error('That file is too big', { description: `The tablet takes up to 64 MB; this is ${size(next.size)}.` })
      return
    }
    setChosen((old) => {
      if (old?.preview) URL.revokeObjectURL(old.preview)
      return {
        file: next,
        preview: next.type.startsWith('image/') ? URL.createObjectURL(next) : null,
      }
    })
    setName(title(next))
  }

  const putDown = () =>
    setChosen((old) => {
      if (old?.preview) URL.revokeObjectURL(old.preview)
      return null
    })

  // Dropping works anywhere, not only on a target: the page is the target.
  // Counted rather than toggled, because dragenter and dragleave fire for
  // every child the pointer crosses.
  useEffect(() => {
    let depth = 0
    const files = (e: DragEvent) => e.dataTransfer?.types.includes('Files') ?? false
    const enter = (e: DragEvent) => {
      if (!files(e)) return
      e.preventDefault()
      depth++
      setDragging(true)
    }
    const over = (e: DragEvent) => {
      if (files(e)) e.preventDefault()
    }
    const leave = (e: DragEvent) => {
      if (!files(e)) return
      depth = Math.max(0, depth - 1)
      if (depth === 0) setDragging(false)
    }
    const drop = (e: DragEvent) => {
      if (!files(e)) return
      e.preventDefault()
      depth = 0
      setDragging(false)
      choose(e.dataTransfer?.files[0])
    }
    window.addEventListener('dragenter', enter)
    window.addEventListener('dragover', over)
    window.addEventListener('dragleave', leave)
    window.addEventListener('drop', drop)
    return () => {
      window.removeEventListener('dragenter', enter)
      window.removeEventListener('dragover', over)
      window.removeEventListener('dragleave', leave)
      window.removeEventListener('drop', drop)
    }
  }, [])

  const send = async () => {
    if (!file) return
    setSending(true)
    try {
      const res = await fetch(`/api/library?name=${encodeURIComponent(name.trim() || title(file))}`, {
        method: 'POST',
        body: file,
        headers: { 'Content-Type': file.type || 'application/octet-stream' },
      })
      const said = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(said.error ?? `the server answered ${res.status}`)
      toast.success(`“${said.name}” is in the library`, {
        description: 'Open it on the tablet once the screen has come back.',
      })
      putDown()
    } catch (err) {
      toast.error('It did not reach the tablet', { description: (err as Error).message })
    } finally {
      setSending(false)
    }
  }

  return (
    <>
      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        onClick={() => picker.current?.click()}
        aria-label="Put a document on the tablet"
        title="Put a pdf, an epub or an image on the tablet"
      >
        <FileUp className="size-4" />
      </Button>
      <input
        ref={picker}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          choose(e.target.files?.[0])
          // Cleared so choosing the same file again still counts as a change.
          e.target.value = ''
        }}
      />
      {dragging && (
        <div className="pointer-events-none fixed inset-4 z-50 flex items-center justify-center rounded-xl border-2 border-dashed border-foreground/30 bg-background/80 backdrop-blur-sm">
          <p className="text-sm text-muted-foreground">Drop it to put it on the tablet</p>
        </div>
      )}
      <Dialog open={file !== null} onOpenChange={(open) => !open && !sending && putDown()}>
        <DialogContent>
          <DialogTitle>Put this on the tablet?</DialogTitle>
          {file && (
            <div className="flex items-center gap-3">
              {preview ? (
                <img src={preview} alt="" className="size-20 shrink-0 rounded-sm border object-contain" />
              ) : (
                <span className="flex size-20 shrink-0 items-center justify-center rounded-sm border text-muted-foreground">
                  <FileText className="size-6" />
                </span>
              )}
              <div className="min-w-0 flex-1 space-y-1">
                <label className="text-xs text-muted-foreground" htmlFor="library-name">
                  Name in the library
                </label>
                <Input
                  id="library-name"
                  value={name}
                  maxLength={120}
                  disabled={sending}
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void send()
                  }}
                />
                <p className="truncate text-xs text-muted-foreground">
                  {file.name} · {size(file.size)}
                </p>
              </div>
            </div>
          )}
          <DialogDescription>
            It becomes a document in the library, rendered by the tablet itself
            {file?.type.startsWith('image/') ? ' as a one-page pdf in greys' : ''}.
            To take it in, the tablet's interface restarts: whatever is open
            closes and the screen reloads for about ten seconds. Then open it
            from the library.
          </DialogDescription>
          <DialogFooter>
            <Button variant="ghost" disabled={sending} onClick={() => putDown()}>
              Not now
            </Button>
            <Button disabled={sending} onClick={() => void send()}>
              {sending ? 'Restarting the tablet…' : 'Put it on the tablet'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
