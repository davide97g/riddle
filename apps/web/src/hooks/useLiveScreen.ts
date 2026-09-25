import { useEffect, useState } from 'react'
import type { LiveMessage } from '@/lib/protocol'

const MAX_BACKOFF = 5000

export type LiveScreen = {
  /** an object url for the newest frame, or null before the first */
  src: string | null
  /** `refused` is the server saying no, which a redial will not change */
  state: 'off' | 'dialing' | 'on' | 'lost' | 'refused'
  message: string | null
  /** `performance.now()` when the frame last changed. Only changed frames
   *  are sent, so this is when somebody last moved the pen, not when the
   *  server last looked. A local clock on purpose: it is only ever compared
   *  with itself. */
  changedAt: number | null
}

const OFF: LiveScreen = { src: null, state: 'off', message: null, changedAt: null }

/** The tablet's screen, for as long as the caller is mounted.
 *
 *  Opening the socket is what asks for the feed and closing it is what ends
 *  it -- the server dials the tablet for the first page watching and hangs
 *  up after the last -- so there is no start or stop message, and a view
 *  left behind in a background tab stops costing the tablet anything when
 *  the browser drops the socket. */
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
      sock = new WebSocket(url)
      sock.binaryType = 'blob'
      sock.onopen = () => {
        attempt = 0
      }
      sock.onmessage = (e) => {
        if (typeof e.data === 'string') {
          const msg: LiveMessage = JSON.parse(e.data)
          setView((v) => ({ ...v, state: msg.state, message: msg.message ?? null }))
          return
        }
        const next = URL.createObjectURL(new Blob([e.data], { type: 'image/png' }))
        const old = shown
        shown = next
        setView((v) => ({ ...v, src: next, changedAt: performance.now() }))
        if (old) window.setTimeout(() => URL.revokeObjectURL(old), 1000)
      }
      sock.onclose = (e) => {
        if (shut) return
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

    connect()
    return () => {
      shut = true
      window.clearTimeout(timer)
      sock?.close()
      if (shown) URL.revokeObjectURL(shown)
    }
  }, [])

  return view
}
