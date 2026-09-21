import { TIMING, WORDMARK } from '@/lib/wordmark'

/** The word, written rather than set.
 *
 *  `draw` runs the nib across it once in `ms`; without it the word is simply
 *  there, which is what the header wants after the splash has already made
 *  the point. The strokes are timed by length rather than by count so the pen
 *  keeps one speed: the dot of the i takes almost no time, the long spine
 *  through `riddl` takes most of it, and the hand reads as a hand. */
export function Wordmark({
  draw = false,
  ms = 1100,
  className,
  ...rest
}: {
  draw?: boolean
  ms?: number
  className?: string
} & React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox={`0 0 ${WORDMARK.width} ${WORDMARK.height}`}
      fill="none"
      stroke="currentColor"
      strokeWidth={WORDMARK.nib}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
      {...rest}
    >
      {WORDMARK.strokes.map((stroke, i) => {
        const { at, span } = TIMING[i]
        return (
          <path
            key={i}
            d={stroke.d}
            // Rounding up: a dasharray a hair short of the path leaves a
            // pinprick of ink showing before the stroke has been drawn.
            strokeDasharray={draw ? stroke.len + 1 : undefined}
            style={
              draw
                ? {
                    strokeDashoffset: stroke.len + 1,
                    animation: `ink-draw ${(span * ms).toFixed(0)}ms linear ${(at * ms).toFixed(0)}ms forwards`,
                  }
                : undefined
            }
          />
        )
      })}
    </svg>
  )
}
