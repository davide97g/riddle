import { Badge } from '@/components/ui/badge'
import { useDiary } from '@/state/RiddleProvider'

export function ConnectionBadge() {
  const { state } = useDiary()
  const look =
    state.conn === 'open'
      ? { dot: 'bg-emerald-500', text: `session ${state.session ?? '-'}` }
      : state.conn === 'connecting'
        ? { dot: 'bg-amber-500 animate-pulse', text: 'connecting' }
        : { dot: 'bg-destructive', text: 'offline' }

  return (
    <Badge variant="outline" className="gap-2 font-normal">
      <span className={`size-2 rounded-full ${look.dot}`} />
      <span className="text-xs">{look.text}</span>
      {state.listening && <span className="text-xs text-muted-foreground">mic</span>}
    </Badge>
  )
}
