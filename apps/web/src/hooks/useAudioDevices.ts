import { useCallback, useEffect, useState } from 'react'

const REMEMBERED = 'riddle.mic'

export type MicDevice = { id: string; label: string }

/** A microphone was chosen once; every later visit should use it again. */
function remembered(): string {
  try {
    return localStorage.getItem(REMEMBERED) ?? ''
  } catch {
    // Safari in private browsing throws on localStorage rather than returning
    // null, and a picker that cannot remember is still a usable picker.
    return ''
  }
}

/** The list of microphones, and which one the page will open.
 *
 *  A browser hides device labels until it has granted the microphone once, so
 *  the list is enumerated again after every successful capture: the first
 *  recording is what turns "Microphone 2" into the name of a real device. */
export function useAudioDevices() {
  const [devices, setDevices] = useState<MicDevice[]>([])
  const [deviceId, setDeviceId] = useState<string>(remembered)
  const [named, setNamed] = useState(false)

  const refresh = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return
    const all = await navigator.mediaDevices.enumerateDevices()
    const mics = all.filter((d) => d.kind === 'audioinput' && d.deviceId !== '')
    setDevices(mics.map((d, i) => ({ id: d.deviceId, label: d.label || `Microphone ${i + 1}` })))
    setNamed(mics.length > 0 && mics.every((d) => d.label !== ''))
  }, [])

  useEffect(() => {
    void refresh()
    // Unplugging the headset that was chosen is not an error until the next
    // recording, but the list should stop offering it immediately.
    navigator.mediaDevices?.addEventListener?.('devicechange', refresh)
    return () => navigator.mediaDevices?.removeEventListener?.('devicechange', refresh)
  }, [refresh])

  /** A browser lists no microphones at all until one has been granted, so
   *  the picker would be empty exactly when it is most wanted. Open the
   *  default microphone for as long as it takes to learn the names, then
   *  let go of it. */
  const reveal = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) return
    try {
      const granted = await navigator.mediaDevices.getUserMedia({ audio: true })
      granted.getTracks().forEach((t) => t.stop())
    } catch {
      // Refused. There is nothing to list, and the mic button will say so
      // properly when it is pressed.
    }
    await refresh()
  }, [refresh])

  const choose = useCallback((id: string) => {
    setDeviceId(id)
    try {
      if (id) localStorage.setItem(REMEMBERED, id)
      else localStorage.removeItem(REMEMBERED)
    } catch {
      // Remembering is a convenience; the choice still holds for this visit.
    }
  }, [])

  /** The remembered microphone is gone. Fall back to the system default
   *  rather than leaving a choice that can only fail. */
  const forget = useCallback(() => choose(''), [choose])

  return { devices, deviceId, choose, forget, refresh, reveal, named }
}
