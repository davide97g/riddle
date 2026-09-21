/** What the diary is doing, said in ink.
 *
 *  Three motifs, and only three, so a glance at the shape of the motion is
 *  enough: dots for thought, a stroke for anything that puts a mark on the
 *  page, bars for anything that is listening. Every one of them is the same
 *  material as the rest of the app -- a line being laid down or lifted -- and
 *  every one is a `currentColor` shape, so the row's own colour carries.
 *
 *  `pathLength="100"` throughout: the dash animation then needs no measuring
 *  and the keyframes are shared.
 */

/** Thinking. Three dots of wet ink, bobbing in sequence.
 *
 *  `still` is for a row that has scrolled into the past. A motion that means
 *  "this is happening" must stop meaning it the moment it stops being true,
 *  or a timeline of finished turns reads as a dozen things all happening at
 *  once. Held still, the dots rest where the animation rests. */
export function InkDots({
  className,
  still = false,
}: {
  className?: string
  still?: boolean
}) {
  return (
    <svg viewBox="0 0 22 10" aria-hidden className={`h-2.5 w-[22px] ${className ?? ''}`}>
      {[3, 11, 19].map((cx, i) => (
        <circle
          key={cx}
          cx={cx}
          cy={6}
          r={2}
          fill="currentColor"
          opacity={still ? 0.4 : undefined}
          className={still ? undefined : 'ink-dot'}
          style={still ? undefined : { animationDelay: `${i * 130}ms` }}
        />
      ))}
    </svg>
  )
}

/** Writing, drawing, rubbing out: a nib crossing a ruled line.
 *
 *  `back` runs it the other way, which is what erasing looks like -- the
 *  stroke retreating into the nib rather than coming out of it. */
export function NibStroke({
  back = false,
  still = false,
}: {
  back?: boolean
  still?: boolean
}) {
  return (
    <svg viewBox="0 0 30 12" aria-hidden className="h-3 w-[30px] shrink-0">
      <path d="M0 10.5H30" stroke="currentColor" strokeOpacity={0.2} strokeWidth={1} />
      <path
        d="M1 9C3.5 2.5 6 10.5 8.5 6.5S13 1.5 15.5 7.5 20 10.5 22.5 5 26 3 29 8"
        pathLength={100}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.75}
        strokeLinecap="round"
        // Held still it keeps no dash offset at all, so what is left is the
        // finished stroke rather than a nib frozen halfway across the line.
        className={still ? undefined : back ? 'nib-lift' : 'nib-lay'}
      />
    </svg>
  )
}

/** Listening, or reading a clip back: the level meter's language, held down
 *  to a glyph. Not the real level -- nothing here knows it -- so it breathes
 *  rather than pretending to measure. */
export function InkWave({ bars = 5 }: { bars?: number }) {
  return (
    <span aria-hidden className="flex h-3 items-center gap-[2px]">
      {Array.from({ length: bars }, (_, i) => (
        <span
          key={i}
          className="ink-bar w-[2px] rounded-full bg-current"
          style={{ animationDelay: `${i * 110}ms` }}
        />
      ))}
    </span>
  )
}

/** The line a motif sits on. Quiet, one line, announced politely: these
 *  arrive unbidden and must not steal a screen reader mid-sentence.
 *
 *  The motif gets a fixed slot rather than its natural width: the three are
 *  different shapes and different sizes, and a status that changes from
 *  thinking to writing should change its motif, not its margin. */
export function StatusLine({
  children,
  motif,
  className = '',
  live = true,
}: {
  children: React.ReactNode
  motif: React.ReactNode
  className?: string
  /** Whether this is still happening. A line about something that finished
   *  three turns ago must not be announced, and must not move. */
  live?: boolean
}) {
  return (
    <p
      aria-live={live ? 'polite' : undefined}
      className={`row-in flex items-center gap-2 px-1 text-xs text-muted-foreground ${className}`}
    >
      <span className="flex w-[30px] shrink-0 justify-center">{motif}</span>
      <span className="min-w-0">{children}</span>
    </p>
  )
}
