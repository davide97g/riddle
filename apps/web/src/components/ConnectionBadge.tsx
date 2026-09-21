import { Badge } from '@/components/ui/badge'
import { InkWave } from '@/components/Status'
import { useDiary } from '@/state/RiddleProvider'

export function ConnectionBadge() {
  const { state } = useDiary()
  // Three states, three kinds of motion: open breathes, connecting pings out
  // and gets nothing back, offline is the only one that holds still.
  const look =
    state.conn === 'open'
      ? { dot: 'bg-live conn-breathe', text: `session ${state.session ?? '-'}` }
      : state.conn === 'connecting'
        ? { dot: 'bg-amber-500 conn-ping', text: 'connecting' }
        : { dot: 'bg-destructive', text: 'offline' }

  return (
    <Badge variant="outline" className="gap-2 font-normal transition-colors">
      <span className={`size-2 rounded-full ${look.dot}`} />
      {/* Keyed so a changing state fades in rather than swapping under you. */}
      <span key={look.text} className="row-in text-xs">
        {look.text}
      </span>
      {state.listening && (
        <span className="row-in text-live" title="The microphone is available">
          <InkWave bars={3} />
          <span className="sr-only">microphone available</span>
        </span>
      )}
    </Badge>
  )
}
