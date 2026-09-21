import { useRef } from 'react'
import { LevelMeter } from '@/components/LevelMeter'
import { MicButton } from '@/components/MicButton'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useAudioCapture } from '@/hooks/useAudioCapture'
import { useDiary } from '@/state/RiddleProvider'

export function Composer() {
  const { state, setDraft, send } = useDiary()
  const level = useRef(0)
  const mic = useAudioCapture(level)
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
          className="max-h-32 min-h-11 flex-1 resize-none"
        />
        <Button onClick={send} disabled={offline} className="h-11">
          Send
        </Button>
      </div>
      <div className="mx-auto mt-2 flex max-w-2xl flex-col items-center gap-1">
        <LevelMeter level={level} live={mic.state === 'recording'} />
        <p className="text-center text-xs text-muted-foreground">
          {!state.listening
            ? 'No speech model loaded, so the microphone is off.'
            : 'Send asks the diary for an answer now. It always answers on the tablet.'}
        </p>
      </div>
    </div>
  )
}
