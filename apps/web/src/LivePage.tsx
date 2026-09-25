import { useEffect, useState } from 'react'
import { LiveScreen } from '@/components/LiveScreen'
import { PageMenu } from '@/components/PageMenu'
import { SendToTablet } from '@/components/SendToTablet'
import { SnapButton, SnapshotShelf, UnderstandButton } from '@/components/Snapshots'
import { Wordmark } from '@/components/Wordmark'
import { useLiveScreen } from '@/hooks/useLiveScreen'
import { useSnapshots } from '@/hooks/useSnapshots'

/** `/live`: the page on the tablet, and nothing else.
 *
 *  A page of its own rather than a mode of the timeline, so it can be left
 *  open on a second screen, bookmarked, or handed to somebody who should see
 *  the notebook without being able to send, erase or stop anything -- there
 *  is no control here that reaches the pen. The one thing it can send the
 *  tablet is a document for its library, which never goes near the pen. */
export function LivePage() {
  const live = useLiveScreen()
  const { snaps, kept, reading, take, remove, understand } = useSnapshots()
  const [open, setOpen] = useState<string | null>(null)
  const act = { remove, understand, reading, open, setOpen }

  useEffect(() => {
    const was = document.title
    document.title = 'riddle · live'
    return () => {
      document.title = was
    }
  }, [])

  return (
    <div className="flex h-dvh flex-col bg-background text-foreground">
      <header className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-3">
          <h1 className="flex items-center">
            <Wordmark className="h-4 w-auto" />
            <span className="sr-only">riddle, live</span>
          </h1>
          <PageMenu current="live" />
        </div>
        <div className="flex items-center gap-2">
          {/* Here as well as on the timeline: this is where you watch it
              arrive. */}
          <SendToTablet />
        </div>
      </header>
      <main className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <LiveScreen
          live={live}
          action={
            <>
              <UnderstandButton
                frame={live.blob}
                take={take}
                understand={understand}
                setOpen={setOpen}
              />
              <SnapButton frame={live.blob} take={take} />
            </>
          }
        />
        <SnapshotShelf snaps={snaps} kept={kept} act={act} />
      </main>
    </div>
  )
}
