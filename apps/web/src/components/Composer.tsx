import { LevelMeter } from '@/components/LevelMeter'
import { MicButton } from '@/components/MicButton'
import { MicPicker } from '@/components/MicPicker'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { VanishSwitch } from '@/components/VanishSwitch'
import type { Microphone } from '@/hooks/useMicrophone'
import { useDiary } from '@/state/RiddleProvider'
import { serving } from '@/state/reducer'

/** What the diary is told, and how.
 *
 *  On a phone this is one row -- the microphone, the line, Send -- and the
 *  switch and the microphone picker live in the menu in the header. The
 *  sentence under the row only speaks there when something is in the way: a
 *  footer that explains itself while everything works is a footer in the
 *  way of the timeline. */
export function Composer({ microphone }: { microphone: Microphone }) {
  const { state, setDraft, send } = useDiary()
  const { level, inputs, mic } = microphone
  const offline = state.conn !== 'open'
  const problem = !state.vanish
    ? 'Vanishing is off: what you write stays on the page, and the diary does not answer.'
    : state.watched === 'live'
      ? 'The page is open on Live, so the diary leaves it alone. Close Live to write to it.'
      : !state.diary.present
        ? 'The diary is not running, so nothing would answer a send.'
        : !serving(state.diary)
          ? 'The diary is waiting for the tablet. Wake it, or check it is on the wifi.'
        : !state.listening
          ? 'No speech model loaded, so the microphone is off.'
          : null

  return (
    <div className="border-t bg-background/80 px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur max-sm:pt-2.5 max-sm:pb-[max(0.5rem,env(safe-area-inset-bottom))]">
      <div className="mx-auto flex max-w-2xl items-end gap-2">
        <MicButton
          state={mic.state}
          start={() => void mic.start()}
          stop={() => void mic.stop()}
          disabled={offline || !state.listening}
        />
        <Textarea
          value={state.draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault()
              send()
            }
          }}
          rows={1}
          enterKeyHint="send"
          placeholder={
            mic.state === 'recording' ? 'listening...' : 'say something to the diary'
          }
          className="max-h-32 min-h-11 flex-1 resize-none transition-[border-color,box-shadow] duration-200 ease-out"
        />
        <Button
          onClick={send}
          disabled={offline || !serving(state.diary) || !state.vanish || state.watched !== null}
          className="h-11 transition-transform duration-150 ease-out active:scale-[0.97] disabled:active:scale-100"
        >
          Send
        </Button>
      </div>
      <div className="mx-auto mt-2 flex max-w-2xl flex-col items-center gap-1 empty:hidden max-sm:mt-1.5">
        <div className="max-sm:hidden">
          <VanishSwitch />
        </div>
        {/* Always on the Mac-sized page, where it idles as a flat line; on a
            phone only while it has something to show. */}
        <div className={mic.state === 'recording' ? '' : 'max-sm:hidden'}>
          <LevelMeter level={level} live={mic.state === 'recording'} />
        </div>
        {state.listening && (
          <div className="max-sm:hidden">
          <MicPicker
            devices={inputs.devices}
            deviceId={inputs.deviceId}
            choose={inputs.choose}
            reveal={() => void inputs.reveal()}
            named={inputs.named}
            // Changing microphone mid-recording would splice two rooms into
            // one sentence; the switch waits until the recording is over.
            disabled={mic.state !== 'idle'}
          />
          </div>
        )}
        {/* Keyed on the sentence: the reason you cannot send changes while
            you are reading it, and a swap without a fade reads as a glitch. */}
        <p
          key={`${state.diary.present}-${state.diary.tablet}-${state.listening}-${state.vanish}-${state.watched}`}
          className={`row-in text-center text-xs text-muted-foreground ${problem ? '' : 'max-sm:hidden'}`}
        >
          {problem ?? 'Send asks the diary for an answer now. It always answers on the tablet.'}
        </p>
      </div>
    </div>
  )
}
