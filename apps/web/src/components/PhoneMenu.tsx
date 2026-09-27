import { Settings2 } from 'lucide-react'
import { MicPicker } from '@/components/MicPicker'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { VanishSwitch } from '@/components/VanishSwitch'
import type { Microphone } from '@/hooks/useMicrophone'
import { useDiary } from '@/state/RiddleProvider'

/** The phone's settings: the switch and the microphone, which on a wider
 *  screen sit under the composer. Only there below `sm`, the same line the
 *  composer hides them at, so each lives in exactly one place at a time. */
export function PhoneMenu({ microphone }: { microphone: Microphone }) {
  const { state } = useDiary()
  const { inputs, mic } = microphone

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button type="button" size="icon-sm" variant="ghost" className="sm:hidden" aria-label="Settings">
          <Settings2 className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-auto min-w-64 gap-3 p-3">
        <VanishSwitch />
        {state.listening && (
          <MicPicker
            devices={inputs.devices}
            deviceId={inputs.deviceId}
            choose={inputs.choose}
            reveal={() => void inputs.reveal()}
            named={inputs.named}
            disabled={mic.state !== 'idle'}
          />
        )}
      </PopoverContent>
    </Popover>
  )
}
