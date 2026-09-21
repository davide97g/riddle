import { ChevronDown, Mic } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { MicDevice } from '@/hooks/useAudioDevices'

/** Which microphone the page listens on.
 *
 *  A native select on purpose: on a phone this is the system picker, which is
 *  the control people already know, and it needs no popover to get wrong.
 *
 *  The list is only named once the microphone has been granted, so before the
 *  first recording the entries read "Microphone 1", "Microphone 2". They are
 *  still the right entries; only the labels are withheld. */
export function MicPicker({
  devices,
  deviceId,
  choose,
  reveal,
  named,
  disabled,
}: {
  devices: MicDevice[]
  deviceId: string
  choose: (id: string) => void
  reveal: () => void
  named: boolean
  disabled?: boolean
}) {
  if (devices.length === 0) {
    return (
      <Button
        type="button"
        variant="ghost"
        size="sm"
        disabled={disabled}
        onClick={reveal}
        className="h-7 gap-1.5 text-xs text-muted-foreground"
      >
        <Mic className="size-3.5" aria-hidden />
        Choose microphone
      </Button>
    )
  }

  // A remembered device that is no longer plugged in would otherwise select
  // nothing and read as the system default, which is not what will happen.
  const missing = deviceId !== '' && !devices.some((d) => d.id === deviceId)

  return (
    <label className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
      <Mic className="size-3.5 shrink-0" aria-hidden />
      <span className="sr-only">Microphone</span>
      <span className="relative flex min-w-0 items-center">
        <select
          value={missing ? '' : deviceId}
          disabled={disabled}
          onChange={(e) => choose(e.target.value)}
          className="max-w-[16rem] min-w-0 appearance-none truncate rounded-md border bg-transparent py-1 pr-6 pl-2 text-xs text-foreground disabled:opacity-60"
        >
          <option value="">System default</option>
          {devices.map((d) => (
            <option key={d.id} value={d.id}>
              {d.label}
            </option>
          ))}
        </select>
        <ChevronDown className="pointer-events-none absolute right-1.5 size-3.5" aria-hidden />
      </span>
      {missing ? (
        <span className="shrink-0">that one is unplugged</span>
      ) : !named ? (
        <span className="shrink-0">names appear after the first recording</span>
      ) : null}
    </label>
  )
}
