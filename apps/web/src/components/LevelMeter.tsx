import { useEffect, useRef } from 'react'

const BARS = 16

/** Sixteen bars, driven straight from the worklet's ref.
 *
 *  Deliberately outside React: twenty updates a second through state would
 *  re-render the composer on every one of them, which a phone notices. */
export function LevelMeter({
  level,
  live,
}: {
  level: React.RefObject<number>
  live: boolean
}) {
  const bars = useRef<(HTMLSpanElement | null)[]>([])

  useEffect(() => {
    if (!live) {
      bars.current.forEach((bar) => bar && (bar.style.transform = 'scaleY(0.12)'))
      return
    }
    let frame = 0
    const tick = () => {
      // Speech covers a wide dynamic range, so the meter is on a curve; a
      // linear one sits dead until someone shouts.
      const loud = Math.min(1, Math.sqrt(level.current) * 2.2)
      bars.current.forEach((bar, i) => {
        if (!bar) return
        const away = Math.abs(i - (BARS - 1) / 2) / ((BARS - 1) / 2)
        const height = Math.max(0.12, loud * (1 - away * 0.65))
        bar.style.transform = `scaleY(${height.toFixed(3)})`
      })
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [level, live])

  return (
    <div className="flex h-4 items-center justify-center gap-[3px]" aria-hidden>
      {Array.from({ length: BARS }, (_, i) => (
        <span
          key={i}
          ref={(el) => {
            bars.current[i] = el
          }}
          className={`h-full w-[3px] origin-center rounded-full ${
            live ? 'bg-live' : 'bg-muted-foreground/40'
          }`}
          // The transform is written every frame while live, so it cannot be
          // transitioned then -- the meter would lag the room. Off, the same
          // bars settle back to rest instead of dropping to it.
          style={{
            transform: 'scaleY(0.12)',
            transition: live
              ? 'background-color 200ms'
              : 'background-color 200ms, transform 280ms var(--ease-lift)',
          }}
        />
      ))}
    </div>
  )
}
