import { Eye } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useDiary } from '@/state/RiddleProvider'

/** The way to `/live`, the page on the tablet as it is right now.
 *
 *  Dead unless the server says it may read the screen: that is
 *  RIDDLE_ALLOW_SNAP, and a link to a page that can only say "refused" would
 *  be a link that lies about where it goes. It does not need the diary --
 *  the feed is its own connection -- so it stays live when the book in the
 *  header is shut. */
export function LiveButton() {
  const { state } = useDiary()
  const ready = state.conn === 'open' && state.live

  if (!ready)
    return (
      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        disabled
        aria-label="Watch the page live"
        title={
          state.conn !== 'open'
            ? 'Not connected, so there is nothing to watch.'
            : 'The server may not read the screen: set RIDDLE_ALLOW_SNAP=1.'
        }
      >
        <Eye className="size-4" />
      </Button>
    )

  return (
    <Button asChild size="icon-sm" variant="ghost">
      <a
        href="/live"
        aria-label="Watch the page live"
        title="Watch the page on the tablet, live"
      >
        <Eye className="size-4" />
      </a>
    </Button>
  )
}
