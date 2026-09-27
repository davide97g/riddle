import { useRef } from 'react'
import { useAudioCapture } from '@/hooks/useAudioCapture'
import { useAudioDevices } from '@/hooks/useAudioDevices'

/** The microphone and the list of them, owned once for the whole page.
 *
 *  Two places need it -- the composer, which records, and the phone's menu
 *  in the header, which picks the device -- and two copies of the device
 *  list would each remember a different choice. */
export function useMicrophone() {
  const level = useRef(0)
  const inputs = useAudioDevices()
  const mic = useAudioCapture(level, inputs)
  return { level, inputs, mic }
}

export type Microphone = ReturnType<typeof useMicrophone>
