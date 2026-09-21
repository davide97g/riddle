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
      className={`size-11 shrink-0 rounded-full ${
        recording ? 'ring-2 ring-emerald-500/60 ring-offset-2 ring-offset-background' : ''
      } ${busy ? 'opacity-60' : ''}`}
    >
      {recording ? <Square className="size-4 fill-current" /> : <Mic className="size-5" />}
    </Button>
  )
}
