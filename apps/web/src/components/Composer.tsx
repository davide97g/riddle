import { useRef } from 'react'
import { LevelMeter } from '@/components/LevelMeter'
import { MicButton } from '@/components/MicButton'
import { MicPicker } from '@/components/MicPicker'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { VanishSwitch } from '@/components/VanishSwitch'
import { useAudioCapture } from '@/hooks/useAudioCapture'
import { useAudioDevices } from '@/hooks/useAudioDevices'
import { useDiary } from '@/state/RiddleProvider'

export function Composer() {
  const { state, setDraft, send } = useDiary()
  const level = useRef(0)
  const inputs = useAudioDevices()
  const mic = useAudioCapture(level, inputs)
  const offline = state.conn !== 'open'

  return (
    <div className="border-t bg-background/80 px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur">
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
          disabled={offline || !state.diary.present || !state.vanish || state.watched !== null}
          className="h-11 transition-transform duration-150 ease-out active:scale-[0.97] disabled:active:scale-100"
        >
          Send
        </Button>
      </div>
      <div className="mx-auto mt-2 flex max-w-2xl flex-col items-center gap-1">
        <VanishSwitch />
        <LevelMeter level={level} live={mic.state === 'recording'} />
        {state.listening && (
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
        )}
        {/* Keyed on the sentence: the reason you cannot send changes while
            you are reading it, and a swap without a fade reads as a glitch. */}
        <p
          key={`${state.diary.present}-${state.listening}-${state.vanish}-${state.watched}`}
          className="row-in text-center text-xs text-muted-foreground"
        >
          {!state.vanish
            ? 'Vanishing is off: what you write stays on the page, and the diary does not answer.'
            : state.watched === 'live'
            ? 'The page is open on Live, so the diary leaves it alone. Close Live to write to it.'
            : state.watched === 'share'
            ? 'A screen is being shared with the tablet, so the diary leaves the page alone.'
            : !state.diary.present
            ? 'The diary is not running, so nothing would answer a send.'
            : !state.listening
              ? 'No speech model loaded, so the microphone is off.'
              : 'Send asks the diary for an answer now. It always answers on the tablet.'}
        </p>
      </div>
    </div>
  )
}
