import { useCallback, useEffect, useRef, useState } from 'react'

/** A screen, window or tab from this browser, for as long as it is shared.
 *
 *  Nothing leaves the browser because of this alone: the stream plays into
 *  a video here, and only a frame somebody chose to send goes anywhere. The
 *  browser's own "stop sharing" bar ends it as well as the page's button,
 *  which is why the track's `ended` is listened for. */
export function useScreenShare() {
  const [stream, setStream] = useState<MediaStream | null>(null)
  const [error, setError] = useState<string | null>(null)
  const video = useRef<HTMLVideoElement>(null)

  const stop = useCallback(() => {
    setStream((old) => {
      old?.getTracks().forEach((track) => track.stop())
      return null
    })
  }, [])

  const start = useCallback(async () => {
    setError(null)
    if (!navigator.mediaDevices?.getDisplayMedia) {
      setError('This browser cannot share a screen. It needs https, or localhost.')
      return
    }
    try {
      const next = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false })
      next.getVideoTracks()[0]?.addEventListener('ended', stop)
      setStream((old) => {
        old?.getTracks().forEach((track) => track.stop())
        return next
      })
    } catch (err) {
      // Pressing cancel in the picker is a NotAllowedError, and not a failure.
      if ((err as DOMException).name !== 'NotAllowedError') setError((err as Error).message)
    }
  }, [stop])

  useEffect(() => {
    if (video.current) video.current.srcObject = stream
  }, [stream])

  useEffect(() => () => stop(), [stop])

  return { stream, error, video, start, stop }
}
