import { useEffect, useState } from 'react'
import { InkWave, StatusLine } from '@/components/Status'
import { INK } from '@/components/rows/Rows'
import { useLiveScreen } from '@/hooks/useLiveScreen'

function ago(ms: number) {
  const s = Math.round(ms / 1000)
  if (s < 2) return 'just now'
  if (s < 60) return `${s}s ago`
  const m = Math.round(s / 60)
  return m < 60 ? `${m} min ago` : `${Math.round(m / 60)} h ago`
}

/** The page on the tablet, as it is right now.
 *
 *  No model, no turn, nothing drawn back: the server reads the screen about
 *  once a second while this is mounted and sends a frame whenever it
 *  changed. It works with the diary stopped, because it never goes through
 *  the half that owns the pen.
 *
 *  The frame is the same opaque greyscale a capture is, so it gets the same
 *  treatment: the paper is dropped in the browser and the ink sits on the
 *  page like any other row. */
export function LiveScreen() {
  const live = useLiveScreen()
  const [inked, setInked] = useState(false)

  // "last change 12s ago" has to count on its own: a page nobody is writing
  // on sends nothing, which is the point.
  const [now, setNow] = useState(() => performance.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(performance.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const said =
    live.state === 'on'
      ? live.changedAt === null
        ? 'live'
        : `live · last change ${ago(now - live.changedAt)}`
      : live.state === 'lost'
        ? `lost the tablet${live.message ? `: ${live.message}` : ''} · redialling`
        : live.state === 'refused'
          ? `the server will not read the screen${live.message ? `: ${live.message}` : ''}`
          : 'dialing the tablet'

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 px-4 py-3">
      <StatusLine
        className="mx-auto w-full max-w-2xl"
        motif={
          live.state === 'on' ? (
            <span className="size-2 rounded-full bg-live conn-breathe" />
          ) : live.state === 'refused' ? (
            <span className="size-2 rounded-full bg-destructive" />
          ) : (
            <InkWave bars={3} />
          )
        }
      >
        <span className="block truncate" title={said}>
          {said}
        </span>
      </StatusLine>
      {/* Sized as a container so the page can be exactly as large as fits:
          the paper is dropped from the image, so the edge is a border on a
          box of the tablet's own proportions, and a box that only
          approximated them would draw an edge that is not the page's. */}
      <div className="mx-auto flex min-h-0 w-full max-w-2xl flex-1 items-center justify-center [container-type:size]">
        {live.src ? (
          <div className="aspect-[1404/1872] w-[min(100cqw,calc(100cqh*1404/1872))] rounded-sm border">
            <img
              src={live.src}
              alt="The page open on the tablet, right now"
              onLoad={() => setInked(true)}
              // A stale frame is still the page, but it must not pass for a
              // live one while the link is down.
              className={`size-full transition-opacity duration-300 ease-out ${
                !inked ? 'opacity-0' : live.state === 'on' ? 'opacity-100' : 'opacity-50'
              } ${INK}`}
            />
          </div>
        ) : (
          <p className="text-center text-sm text-muted-foreground">
            {live.state === 'refused'
              ? 'Set RIDDLE_ALLOW_SNAP=1 on the server to watch the page.'
              : 'Waiting for the first frame.'}
          </p>
        )}
      </div>
    </div>
  )
}
