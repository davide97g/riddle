import { Switch } from '@/components/ui/switch'
import { useDiary } from '@/state/RiddleProvider'

/** The trick itself, on or off.
 *
 *  On, a pause of three seconds is a question: your ink fades and the diary
 *  writes back. Off, a pause is only a pause and what you write stays where
 *  you wrote it -- for notes, sketches, anything meant to be kept. Send is
 *  off with it, because an answer would land on writing that is staying.
 *
 *  Kept in the store, so the loop obeys it with no page open, and in this
 *  browser. Whatever it says, the diary never touches the page while
 *  somebody is watching it live. */
export function VanishSwitch() {
  const { state, setVanish } = useDiary()
  const offline = state.conn !== 'open'

  return (
    <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground has-disabled:cursor-not-allowed">
      <Switch
        checked={state.vanish}
        onCheckedChange={setVanish}
        disabled={offline}
        aria-describedby="vanish-says"
      />
      <span className="text-foreground">Vanish and answer</span>
      <span id="vanish-says" className="sr-only">
        {state.vanish
          ? 'After a pause your writing fades and the diary answers.'
          : 'Your writing stays on the page and the diary does not answer.'}
      </span>
    </label>
  )
}
