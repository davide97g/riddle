import { Eye } from 'lucide-react'
import { Button } from '@/components/ui/button'

/** Where the composer is for the owner, for somebody who came in as a guest.
 *
 *  Nothing on this page can reach the pen for a guest -- the server refuses
 *  it whatever the page says -- so there is nothing to press but the way to
 *  the password, for the one guest who has it. */
export function GuestNote() {
  return (
    <div className="border-t bg-background/80 px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur">
      <div className="mx-auto flex max-w-2xl items-center gap-3">
        <Eye className="size-4 shrink-0 text-muted-foreground" />
        <p className="flex-1 text-xs text-muted-foreground">
          Reading as a guest: everything written so far, and what is written
          next, as it happens. Nothing here reaches the pen.
        </p>
        <Button asChild size="sm" variant="outline">
          <a href="/login">Sign in</a>
        </Button>
      </div>
    </div>
  )
}
