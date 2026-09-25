import { useEffect, useState } from 'react'
import type { LiveMessage } from '@/lib/protocol'

const MAX_BACKOFF = 5000

export type LiveScreen = {
  /** an object url for the newest frame, or null before the first */
  src: string | null
  /** the same frame as a blob, for copying and keeping without a refetch */
  blob: Blob | null
  /** `refused` is the server saying no, which a redial will not change */
  state: 'off' | 'dialing' | 'on' | 'lost' | 'refused'
  message: string | null
  /** `performance.now()` when the frame last changed. Only changed frames
   *  are sent, so this is when somebody last moved the pen, not when the
   *  server last looked. A local clock on purpose: it is only ever compared
   *  with itself. */
  changedAt: number | null
}

const OFF: LiveScreen = { src: null, blob: null, state: 'off', message: null, changedAt: null }

/** The tablet's screen, for as long as the caller is mounted.
 *
 *  Opening the socket is what asks for the feed and closing it is what ends
 *  it -- the server dials the tablet for the first page watching and hangs
 *  up after the last -- so there is no start or stop message.
 *
 *  Only while the tab can be seen. A browser keeps a background tab's socket
 *  open for as long as the tab exists, and an open feed is somebody watching
 *  as far as the diary knows: it keeps its hands off the page. A Live tab
 *  left behind while you write in the Diary one would stop the diary for
 *  good, so hiding the tab hangs up and showing it dials again. */
export function useLiveScreen(): LiveScreen {
  const [view, setView] = useState<LiveScreen>(OFF)

  useEffect(() => {
    let shut = false
    let timer: number | undefined
    let attempt = 0
    let sock: WebSocket | null = null
    // Revoked one frame late, once the img has moved on to the next url.
    let shown: string | null = null

    const connect = () => {
      const url = new URL('/ws/live', window.location.href)
      url.protocol = url.protocol.replace('http', 'ws')
      const me = new WebSocket(url)
      sock = me
      me.binaryType = 'blob'
      me.onopen = () => {
        attempt = 0
      }
      me.onmessage = (e) => {
        if (typeof e.data === 'string') {
          const msg: LiveMessage = JSON.parse(e.data)
          setView((v) => ({ ...v, state: msg.state, message: msg.message ?? null }))
          return
        }
        const blob = new Blob([e.data], { type: 'image/png' })
        const next = URL.createObjectURL(blob)
        const old = shown
        shown = next
        setView((v) => ({ ...v, src: next, blob, changedAt: performance.now() }))
        if (old) window.setTimeout(() => URL.revokeObjectURL(old), 1000)
      }
      me.onclose = (e) => {
        // Hung up on purpose, by leaving or by hiding the tab.
        if (shut || sock !== me) return
        // 1008 is the gate: RIDDLE_ALLOW_SNAP is off, and asking again every
        // few seconds will not turn it on.
        if (e.code === 1008) {
          setView((v) => ({ ...v, state: 'refused', message: e.reason || null }))
          return
        }
        setView((v) => ({ ...v, state: 'lost', message: 'lost the server' }))
        const wait = Math.min(MAX_BACKOFF, 250 * 2 ** attempt++)
        timer = window.setTimeout(connect, wait * (0.7 + Math.random() * 0.6))
      }
    }

    const hangUp = () => {
      window.clearTimeout(timer)
      const was = sock
      sock = null
      was?.close()
    }
    const seen = () => {
      if (document.hidden) {
        hangUp()
        // The last frame stays up, faded: it is what the page was when you
        // looked away, and it is replaced as soon as the feed is back.
        setView((v) => ({ ...v, state: 'off', message: null }))
      } else if (sock === null) {
        attempt = 0
        setView((v) => ({ ...v, state: 'dialing', message: null }))
        connect()
      }
    }

    if (!document.hidden) connect()
    document.addEventListener('visibilitychange', seen)
    return () => {
      shut = true
      document.removeEventListener('visibilitychange', seen)
      hangUp()
      if (shown) URL.revokeObjectURL(shown)
    }
  }, [])

  return view
}
