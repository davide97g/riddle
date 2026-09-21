import { useEffect, useRef, useState } from 'react'
import { Wordmark } from '@/components/Wordmark'

/** How long the splash is held, whatever the socket is doing. Cosmetic on
 *  purpose: the page has nothing to wait for, so the only honest reason to
 *  hold it is that watching the word get written is the point. */
const HOLD_MS = 1400
/** The nib finishes with a beat to spare, so the word is a word before it
 *  moves rather than still being drawn as it leaves. */
const DRAW_MS = 1050
/** The flight up into the header. Shorter than the draw: leaving should feel
 *  quicker than arriving. */
const FLIGHT_MS = 460

const REDUCED = '(prefers-reduced-motion: reduce)'

/** The word writes itself, then flies into the header and becomes the title.
 *
 *  It is one element the whole way: the mark that lands is measured against
 *  the real header mark and animated onto it, so nothing crossfades and
 *  nothing jumps. `onDone` and this component's own exit are set in the same
 *  callback, which React commits together -- reveal the header mark a frame
 *  early or a frame late and the handoff shows. */
export function Splash({ onDone }: { onDone: () => void }) {
  const [gone, setGone] = useState(false)
  const mark = useRef<SVGSVGElement>(null)
  const sheet = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const calm = window.matchMedia(REDUCED).matches
    const finish = () => {
      onDone()
      setGone(true)
    }
    const timer = window.setTimeout(
      () => {
        const from = mark.current?.getBoundingClientRect()
        const to = document
          .querySelector('[data-wordmark="header"]')
          ?.getBoundingClientRect()
        sheet.current?.animate([{ opacity: 1 }, { opacity: 0 }], {
          duration: FLIGHT_MS,
          easing: 'cubic-bezier(0.4, 0, 1, 1)',
          fill: 'forwards',
        })
        // No header to fly to (or nobody wants the motion): fade and be done.
        if (calm || !from || !to || !from.width || !to.width) {
          const out = mark.current?.animate([{ opacity: 1 }, { opacity: 0 }], {
            duration: calm ? 120 : FLIGHT_MS,
            fill: 'forwards',
          })
          if (out) out.onfinish = finish
          else finish()
          return
        }
        const flight = mark.current!.animate(
          [
            { transform: 'none' },
            {
              transform: `translate(${to.left - from.left}px, ${to.top - from.top}px) scale(${to.width / from.width})`,
            },
          ],
          {
            duration: FLIGHT_MS,
            // Into the corner with intent, settling rather than braking.
            easing: 'cubic-bezier(0.66, 0, 0.34, 1)',
            fill: 'forwards',
          },
        )
        flight.onfinish = finish
      },
      calm ? 400 : HOLD_MS,
    )
    return () => window.clearTimeout(timer)
  }, [onDone])

  if (gone) return null
  return (
    <div
      ref={sheet}
      // Above everything, and deaf to touch: a splash that swallows the first
      // tap is a splash that cost you something.
      className="pointer-events-none fixed inset-0 z-50 grid place-items-center bg-background"
    >
      <div className="flex flex-col items-center gap-3">
        <Wordmark
          ref={mark}
          draw={!window.matchMedia(REDUCED).matches}
          ms={DRAW_MS}
          // The transform origin has to be the corner the flight is measured
          // from, or the landing is off by half the word.
          style={{ transformOrigin: '0 0' }}
          className="h-[clamp(3.25rem,19vw,5.25rem)] w-auto text-foreground"
        />
        <span className="splash-rule h-px w-[clamp(9rem,42vw,14rem)] bg-foreground/15" />
      </div>
      <span className="sr-only">riddle</span>
    </div>
  )
}
