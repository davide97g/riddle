import { useEffect } from 'react'
import { ArrowLeft } from 'lucide-react'
import { LiveScreen } from '@/components/LiveScreen'
import { Wordmark } from '@/components/Wordmark'
import { Button } from '@/components/ui/button'

/** `/live`: the page on the tablet, and nothing else.
 *
 *  A page of its own rather than a mode of the timeline, so it can be left
 *  open on a second screen, bookmarked, or handed to somebody who should see
 *  the notebook without being able to send, erase or stop anything -- there
 *  is no control here that reaches the pen. */
export function LivePage() {
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
        <h1 className="flex items-center gap-2">
          <Wordmark className="h-4 w-auto" />
          <span className="text-xs uppercase tracking-wide text-muted-foreground">
            live
          </span>
          <span className="sr-only">riddle, live</span>
        </h1>
        <Button asChild size="icon-sm" variant="ghost">
          <a href="/" aria-label="Back to the timeline" title="Back to the timeline">
            <ArrowLeft className="size-4" />
          </a>
        </Button>
      </header>
      <LiveScreen />
    </div>
  )
}
