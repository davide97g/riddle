import { Composer } from '@/components/Composer'
import { ConnectionBadge } from '@/components/ConnectionBadge'
import { Timeline } from '@/components/Timeline'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useDiary } from '@/state/RiddleProvider'

export default function App() {
  const { state } = useDiary()
  return (
    // dvh, not vh: safari's collapsing toolbar makes vh lie about the height
    // and the composer ends up under the home indicator.
    <div className="flex h-dvh flex-col bg-background text-foreground">
      <header className="flex items-center justify-between border-b px-4 py-3">
        <h1 className="text-sm font-medium tracking-wide">riddle</h1>
        <ConnectionBadge />
      </header>
      {state.conn === 'closed' && (
        <Alert className="rounded-none border-x-0 border-t-0">
          <AlertDescription>
            Not connected to the diary. Is <code>./voice.sh start</code> running?
          </AlertDescription>
        </Alert>
      )}
      <Timeline />
      <Composer />
    </div>
  )
}
