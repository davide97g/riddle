import { useEffect, useState } from 'react'
import { Eraser, ScreenShare, ScreenShareOff, Send } from 'lucide-react'
import { toast } from 'sonner'
import { PageMenu } from '@/components/PageMenu'
import { InkWave, StatusLine } from '@/components/Status'
import { Wordmark } from '@/components/Wordmark'
import { Button } from '@/components/ui/button'
import { useScreenShare } from '@/hooks/useScreenShare'
import { useShareInk } from '@/hooks/useShareInk'
import { putInLibrary } from '@/lib/library'
import { grab, onPage } from '@/lib/share'
import type { Orientation, Still } from '@/lib/share'

/** A box of the page's own shape, as large as fits, like the live view's. */
const BOX: Record<Orientation, string> = {
  portrait: 'aspect-[1404/1872] w-[min(100cqw,calc(100cqh*1404/1872))]',
  landscape: 'aspect-[1872/1404] w-[min(100cqw,calc(100cqh*1872/1404))]',
}

function clock() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/** `/share`: a screen from this browser, written on at the tablet.
 *
 *  One frame at a time, and on purpose. The tablet has no way to be shown a
 *  picture but as a document in its library, and putting one there restarts
 *  xochitl -- ten seconds of the screen reloading, and then the document has
 *  to be opened by hand. So a frame goes when it is asked for, never on a
 *  timer, and the way back is the fast half: every stroke written on it
 *  comes back over the socket as it ends, and is drawn here over the shared
 *  screen, or over the frame it was written on.
 *
 *  While this page shares, the diary keeps its hands off the page, and the
 *  strokes come back only while the diary is running: it is what holds the
 *  pen. */
export function SharePage() {
  const { stream, error, video, start, stop } = useScreenShare()
  const sharing = stream !== null
  const ink = useShareInk(sharing)
  const [still, setStill] = useState<(Still & { name: string }) | null>(null)
  const [sending, setSending] = useState(false)
  const [over, setOver] = useState<'screen' | 'frame'>('screen')
  // The shape of the stage before any frame is sent: the shared screen's own.
  const [shape, setShape] = useState<Orientation>('landscape')

  useEffect(() => {
    const was = document.title
    document.title = 'riddle · share'
    return () => {
      document.title = was
    }
  }, [])

  useEffect(() => () => {
    if (still) URL.revokeObjectURL(still.url)
  }, [still])

  const send = async () => {
    if (!video.current) return
    setSending(true)
    try {
      const next = await grab(video.current)
      const name = `Share ${clock()}`
      // Before the upload rather than after it: the stroke written the moment
      // the document opens belongs to this frame, not the last one.
      ink.mark()
      const said = await putInLibrary(next.blob, name)
      setStill({ ...next, name: said.name ?? name })
      setOver('screen')
      toast.success(`“${said.name ?? name}” is in the library`, {
        description: 'Open it on the tablet once the screen has come back, and write.',
      })
    } catch (err) {
      toast.error('The frame did not reach the tablet', { description: (err as Error).message })
    } finally {
      setSending(false)
    }
  }

  const orientation = still?.orientation ?? shape
  const showing = still && (over === 'frame' || !sharing) ? 'frame' : 'screen'

  const said = !sharing
    ? still
      ? `stopped sharing · “${still.name}” is still on the tablet`
      : error ?? 'share a screen, then send a frame of it to the tablet'
    : sending
      ? 'putting the frame on the tablet · the screen reloads for about ten seconds'
      : !still
        ? 'sharing · send a frame to write on it'
        : ink.diary && !ink.diary.present
          ? 'the diary is not running, and the strokes come back through it'
          : `“${still.name}” on the tablet · ${ink.strokes.length} stroke${ink.strokes.length === 1 ? '' : 's'}`

  return (
    <div className="flex h-dvh flex-col bg-background text-foreground">
      <header className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-3">
          <h1 className="flex items-center">
            <Wordmark className="h-4 w-auto" />
            <span className="sr-only">riddle, share</span>
          </h1>
          <PageMenu current="share" />
        </div>
      </header>
      <main className="flex min-h-0 flex-1 flex-col gap-2 px-4 py-3">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center gap-2">
          <StatusLine
            className="min-w-0 flex-1"
            live={sharing}
            motif={
              sending ? (
                <InkWave bars={3} />
              ) : (
                <span className={`size-2 rounded-full ${sharing ? 'bg-live conn-breathe' : 'bg-muted-foreground/40'}`} />
              )
            }
          >
            <span className="block truncate" title={said}>
              {said}
            </span>
          </StatusLine>
          {still && sharing && (
            <div className="flex items-center rounded-md border p-0.5" role="group" aria-label="Draw the ink over">
              {(['screen', 'frame'] as const).map((what) => (
                <Button
                  key={what}
                  size="xs"
                  variant={over === what ? 'secondary' : 'ghost'}
                  aria-pressed={over === what}
                  onClick={() => setOver(what)}
                  title={what === 'screen' ? 'Over the screen as it is now' : 'Over the frame the tablet has'}
                >
                  {what === 'screen' ? 'Screen' : 'Frame'}
                </Button>
              ))}
            </div>
          )}
          {still && (
            <Button size="sm" variant="ghost" onClick={ink.clear} disabled={ink.strokes.length === 0} title="Clear the ink on this page; the tablet keeps its own">
              <Eraser />
              Clear
            </Button>
          )}
          {sharing ? (
            <>
              <Button size="sm" variant="ghost" onClick={stop}>
                <ScreenShareOff />
                Stop
              </Button>
              <Button
                size="sm"
                onClick={() => void send()}
                disabled={sending}
                title="Restarts the tablet's screen (about ten seconds), then open the frame from its library"
              >
                <Send />
                {sending ? 'Sending…' : still ? 'Send a new frame' : 'Send frame'}
              </Button>
            </>
          ) : (
            <Button size="sm" onClick={() => void start()}>
              <ScreenShare />
              Share a screen
            </Button>
          )}
        </div>
        <div className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 items-center justify-center [container-type:size]">
          <div className={`relative overflow-hidden rounded-sm border bg-white ${BOX[orientation]} ${sharing || still ? '' : 'hidden'}`}>
            {/* Always mounted while sharing: a frame is grabbed from it even
                while the ink is drawn over the frame instead. */}
            <video
              ref={video}
              autoPlay
              muted
              playsInline
              onLoadedMetadata={(e) => {
                const v = e.currentTarget
                setShape(v.videoWidth > v.videoHeight ? 'landscape' : 'portrait')
              }}
              onResize={(e) => {
                const v = e.currentTarget
                if (v.videoWidth) setShape(v.videoWidth > v.videoHeight ? 'landscape' : 'portrait')
              }}
              className={`absolute inset-0 size-full object-contain ${showing === 'screen' ? '' : 'invisible'}`}
            />
            {still && showing === 'frame' && (
              <img src={still.url} alt="The frame on the tablet" className="absolute inset-0 size-full" />
            )}
            {still && (
              <svg
                viewBox={`0 0 ${still.width} ${still.height}`}
                className="pointer-events-none absolute inset-0 size-full text-annotate"
                aria-label={`${ink.strokes.length} strokes written on the tablet`}
              >
                {ink.strokes.map((stroke) => (
                  <polyline
                    key={stroke.id}
                    points={stroke.points.map(([x, y]) => onPage(x, y, still.orientation).join(',')).join(' ')}
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={4}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                ))}
              </svg>
            )}
          </div>
          {!sharing && !still && (
            <p className="max-w-sm text-center text-sm text-muted-foreground">
              Pick a screen, a window or a tab. Nothing leaves this browser until
              you send a frame; then write on it at the tablet and the ink shows
              up here.
            </p>
          )}
        </div>
      </main>
    </div>
  )
}
