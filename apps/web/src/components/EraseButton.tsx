import { useState } from 'react'
import { Eraser } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from '@/components/ui/dialog'
import { useDiary } from '@/state/RiddleProvider'

/** Start again: the ink off the page, the conversation dropped, the timeline
 *  deleted. It asks first, because only one of those three can be undone and
 *  it is not the ink.
 *
 *  Only the loop can do any of it -- it owns the pen and the geometry of what
 *  it drew -- so with the diary not running the button is dead rather than
 *  quietly leaving an intent nothing will ever serve. */
export function EraseButton() {
  const { state, clear } = useDiary()
  const [asking, setAsking] = useState(false)
  const ready = state.conn === 'open' && state.diary.present

  return (
    <>
      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        disabled={!ready}
        onClick={() => setAsking(true)}
        className="group"
        aria-label="Erase this conversation"
        title={
          ready
            ? 'Erase this conversation'
            : 'The diary is not running, so nothing can rub the page out.'
        }
      >
        {/* The eraser tips into the page on hover, the way you would hold
            it. It is the only destructive control here; a hair of motion is
            what says so before the dialog does. */}
        <Eraser className="size-4 transition-transform duration-200 ease-out group-hover:-rotate-12 group-active:scale-90" />
      </Button>
      <Dialog open={asking} onOpenChange={setAsking}>
        <DialogContent>
          <DialogTitle>Erase this conversation?</DialogTitle>
          <DialogDescription>
            The diary rubs its own ink off the page, starts a new conversation
            and deletes this session from the timeline, along with the captures
            and recordings it kept. What it wrote to memory survives. The ink
            cannot be brought back.
          </DialogDescription>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAsking(false)}>
              Keep it
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                clear()
                setAsking(false)
              }}
            >
              Erase
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
