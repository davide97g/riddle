import { Mic, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { CaptureState } from '@/hooks/useAudioCapture'

export function MicButton({
  state,
  start,
  stop,
  disabled,
}: {
  state: CaptureState
  start: () => void
  stop: () => void
  disabled?: boolean
}) {
  const recording = state === 'recording'
  // `stopping` is not decoration: closing the socket and reading the tail of
  // the sentence takes a moment, and without it the button looks broken.
  const busy = state === 'requesting' || state === 'stopping'

  return (
    <Button
      type="button"
      size="icon"
      variant={recording ? 'default' : 'secondary'}
      disabled={disabled || busy}
      onClick={() => (recording ? stop() : start())}
      aria-label={recording ? 'Stop listening' : 'Start listening'}
      // The press shrinks under the thumb and the halo only exists while
      // something is being recorded, so the one animated thing in the
      // composer is the one thing that is running.
      className={`relative size-11 shrink-0 rounded-full transition-transform duration-150 ease-out active:scale-95 ${
        recording ? 'mic-live ring-2 ring-live/60 ring-offset-2 ring-offset-background' : ''
      } ${busy ? 'opacity-60' : ''}`}
    >
      {/* Keyed so the two glyphs cross rather than cut: the square turns in
          as the nib turns out, which is the same gesture as pressing it. */}
      <span key={recording ? 'stop' : 'go'} className="mic-swap">
        {recording ? (
          <Square className="size-4 fill-current" />
        ) : (
          <Mic className="size-5" />
        )}
      </span>
    </Button>
  )
}
