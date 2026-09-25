import { useEffect, useState } from 'react'
import { InkWave, StatusLine } from '@/components/Status'
import { lookClass } from '@/hooks/useLook'
import type { Look } from '@/hooks/useLook'
import type { LiveScreen as Feed } from '@/hooks/useLiveScreen'

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
 *  page like any other row.
 *
 *  `action` sits at the end of the status line, which is where the one thing
 *  you can do with a live page goes. */
export function LiveScreen({
  live,
  action,
  look,
}: {
  live: Feed
  action?: React.ReactNode
  look: Look
}) {
  const [inked, setInked] = useState(false)
  // The frame's own proportions, read off it as it loads: the server turns
  // a landscape page before sending it, so a frame is 1404x1872 or
  // 1872x1404, and the box that draws the paper's edge follows it.
  const [ratio, setRatio] = useState(1404 / 1872)

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
          : live.state === 'off'
            ? 'paused while this tab is hidden'
            : 'dialing the tablet'

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 px-4 py-3">
      <div className="mx-auto flex w-full max-w-5xl items-center gap-2">
        <StatusLine
          className="min-w-0 flex-1"
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
        {action}
      </div>
      {/* Sized as a container so the page can be exactly as large as fits:
          the paper is dropped from the image, so the edge is a border on a
          box of the tablet's own proportions, and a box that only
          approximated them would draw an edge that is not the page's. */}
      {/* As wide as a landscape page can use: a portrait one is held by the
          height anyway, so the extra width only ever goes to landscape. */}
      <div className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 items-center justify-center [container-type:size]">
        {live.src ? (
          <div
            className="aspect-(--ratio) w-[min(100cqw,calc(100cqh*var(--ratio)))] rounded-sm border"
            style={{ '--ratio': ratio } as React.CSSProperties}
          >
            <img
              src={live.src}
              alt="The page open on the tablet, right now"
              onLoad={(e) => {
                const img = e.currentTarget
                setInked(true)
                if (img.naturalWidth && img.naturalHeight)
                  setRatio(img.naturalWidth / img.naturalHeight)
              }}
              // A stale frame is still the page, but it must not pass for a
              // live one while the link is down.
              className={`size-full transition-opacity duration-300 ease-out ${
                !inked ? 'opacity-0' : live.state === 'on' ? 'opacity-100' : 'opacity-50'
              } ${lookClass(look)}`}
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
