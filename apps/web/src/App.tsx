import { useCallback, useState } from 'react'
import { Composer } from '@/components/Composer'
import { ConnectionBadge } from '@/components/ConnectionBadge'
import { DiaryButton } from '@/components/DiaryButton'
import { EraseButton } from '@/components/EraseButton'
import { PageMenu } from '@/components/PageMenu'
import { SendToTablet } from '@/components/SendToTablet'
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
  // Live is dead unless the server says it may read the screen: that is
  // RIDDLE_ALLOW_SNAP. It does not need the diary -- the feed is its own
  // connection -- so it stays open when the book in the header is shut.
  const liveOff =
    state.conn !== 'open'
      ? 'Not connected, so there is nothing to watch.'
      : state.live
        ? undefined
        : 'The server may not read the screen: set RIDDLE_ALLOW_SNAP=1.'

  return (
    // dvh, not vh: safari's collapsing toolbar makes vh lie about the height
    // and the composer ends up under the home indicator.
    <div className="flex h-dvh flex-col bg-background text-foreground">
      <header className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-3">
          <h1 className="flex items-center">
            <Wordmark
              data-wordmark="header"
              className={`h-4 w-auto ${booted ? 'opacity-100' : 'opacity-0'}`}
            />
            <span className="sr-only">riddle</span>
          </h1>
          <PageMenu current="diary" off={{ live: liveOff }} />
        </div>
        <div className="flex items-center gap-2">
          <DiaryButton />
          <SendToTablet />
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
