import { useCallback, useState } from 'react'
import { Composer } from '@/components/Composer'
import { ConnectionBadge } from '@/components/ConnectionBadge'
import { DiaryButton } from '@/components/DiaryButton'
import { EraseButton } from '@/components/EraseButton'
import { Splash } from '@/components/Splash'
import { Timeline } from '@/components/Timeline'
import { Wordmark } from '@/components/Wordmark'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useDiary } from '@/state/RiddleProvider'

export default function App() {
  const { state } = useDiary()
  // The header mark is the thing the splash flies onto, so it has to be laid
  // out and measurable the whole time -- hidden, not absent.
  const [booted, setBooted] = useState(false)
  const done = useCallback(() => setBooted(true), [])

  return (
    // dvh, not vh: safari's collapsing toolbar makes vh lie about the height
    // and the composer ends up under the home indicator.
    <div className="flex h-dvh flex-col bg-background text-foreground">
      <header className="flex items-center justify-between border-b px-4 py-3">
        <h1 className="flex items-center">
          <Wordmark
            data-wordmark="header"
            className={`h-4 w-auto ${booted ? 'opacity-100' : 'opacity-0'}`}
          />
          <span className="sr-only">riddle</span>
        </h1>
        <div className="flex items-center gap-2">
          <DiaryButton />
          <ConnectionBadge />
          <EraseButton />
        </div>
      </header>
      {state.conn === 'closed' && (
        <Alert className="drop-in rounded-none border-x-0 border-t-0">
          <AlertDescription>
            Not connected to the diary. Is <code>riddle voice start</code>{' '}
            running?
          </AlertDescription>
        </Alert>
      )}
      <Timeline />
      <Composer />
      <Splash onDone={done} />
    </div>
  )
}
