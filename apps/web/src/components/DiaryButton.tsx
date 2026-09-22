import { useState } from 'react'
import { DiaryIcon } from '@/components/DiaryIcon'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from '@/components/ui/dialog'
import { useDiary } from '@/state/RiddleProvider'

/** The book in the header, made into the switch for the half it draws.
 *
 *  Everything else on this page needs the loop to already be running -- Send,
 *  Erase, and the answer to anything you say. This is the one control that is
 *  for when it is *not*, which is why it is the status light itself rather
 *  than a button beside it: the thing that tells you the diary is shut is the
 *  thing you press to open it.
 *
 *  Starting asks nothing. Stopping does, because the loop may be halfway
 *  through a stroke on a real page and there is no undo for a line that stops
 *  in the middle of a word.
 *
 *  Nothing here is optimistic. The cover swings when the loop's heartbeat
 *  reaches the store and the server says so, seconds after the press --
 *  anything sooner would be the page claiming a pen it has not got. */
export function DiaryButton() {
  const { state, runDiary } = useDiary()
  const { present, busy, manager } = state.diary
  const [asking, setAsking] = useState(false)
  const offline = state.conn !== 'open'

  return (
    <>
      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        disabled={offline || busy}
        onClick={() => (present ? setAsking(true) : runDiary(true))}
        aria-label={present ? 'Stop the diary' : 'Start the diary'}
        title={
          offline
            ? 'Not connected, so there is nothing to ask.'
            : busy
              ? 'Working on it.'
              : present
                ? 'The diary is running and will answer a send. Press to stop it.'
                : 'The diary is not running. Press to start it.'
        }
      >
        {/* Unlabelled: the button carries the name and the tooltip now, and
            two of each on one target is one too many for a screen reader. */}
        <DiaryIcon open={present} busy={busy} labelled={false} />
      </Button>
      <Dialog open={asking} onOpenChange={setAsking}>
        <DialogContent>
          <DialogTitle>Stop the diary?</DialogTitle>
          <DialogDescription>
            The half that owns the pen goes down: the link to the tablet
            closes, anything it was drawing stops where it is, and nothing
            will answer a send until it is started again.{' '}
            {manager === 'systemd'
              ? 'It is a service here, so it stays down until it is asked back.'
              : 'It is started again from this page, or with riddle diary start.'}{' '}
            What is written stays written.
          </DialogDescription>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAsking(false)}>
              Leave it running
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                runDiary(false)
                setAsking(false)
              }}
            >
              Stop it
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
