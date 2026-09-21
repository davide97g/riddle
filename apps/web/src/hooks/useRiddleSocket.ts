import { useCallback, useEffect, useRef } from 'react'
import type { Action } from '@/state/reducer'
import type { ClientMessage, ServerMessage } from '@/lib/protocol'

const MAX_BACKOFF = 5000
const HEARTBEAT = 15000
const PONG_DEADLINE = 10000

/** The socket is the source of truth, not a cache to invalidate.
 *
 *  Every persisted event carries a monotonic id, so reconnecting is
 *  `hello { since }` and the reducer's dedupe absorbs the overlap. There is no
 *  other resync path and there does not need to be one. */
export function useRiddleSocket(
  dispatch: (action: Action) => void,
  /** called when the server acknowledges a send, with its intent id */
  onIntent?: (id: number) => void,
) {
  const ws = useRef<WebSocket | null>(null)
  // Held in a ref so a new callback identity does not tear the socket down
  // and redial it on every render, and written in an effect rather than
  // during render, which is not a safe place to touch one.
  const onIntentRef = useRef(onIntent)
  useEffect(() => {
    onIntentRef.current = onIntent
  }, [onIntent])
  const seq = useRef(0)
  const attempt = useRef(0)
  const shut = useRef(false)

  const send = useCallback((msg: ClientMessage) => {
    const sock = ws.current
    if (sock?.readyState === WebSocket.OPEN) sock.send(JSON.stringify(msg))
    // Dropped on purpose while closed. A turn queued now and delivered in four
    // minutes would draw on whatever page is open then.
  }, [])

  useEffect(() => {
    let timer: number | undefined
    let beat: number | undefined
    let lastPong = Date.now()
    // Refs survive StrictMode's mount, unmount, mount. Without this the
    // cleanup from the first pass leaves the flag set and the second pass
    // never dials, which looks exactly like the server being down.
    shut.current = false

    const connect = () => {
      if (shut.current) return
      dispatch({ type: 'conn', conn: 'connecting' })

      const url = new URL('/ws/events', window.location.href)
      url.protocol = url.protocol.replace('http', 'ws')
      const sock = new WebSocket(url)
      ws.current = sock

      sock.onopen = () => {
        attempt.current = 0
        lastPong = Date.now()
        sock.send(JSON.stringify({ type: 'hello', since: seq.current, limit: 500 }))
        beat = window.setInterval(() => {
          if (Date.now() - lastPong > HEARTBEAT + PONG_DEADLINE) {
            sock.close()
            return
          }
          sock.send(JSON.stringify({ type: 'ping', t: Date.now() }))
        }, HEARTBEAT)
      }

      sock.onmessage = (e) => {
        const msg: ServerMessage = JSON.parse(e.data)
        if (msg.type === 'pong') {
          lastPong = Date.now()
          return
        }
        if (msg.type === 'hello.ok') lastPong = Date.now()
        if (msg.type === 'intent.ok') {
          onIntentRef.current?.(msg.id)
          return
        }
        if (msg.type === 'event') seq.current = Math.max(seq.current, msg.id)
        dispatch({ type: 'server', msg })
      }

      sock.onclose = () => {
        window.clearInterval(beat)
        dispatch({ type: 'conn', conn: 'closed' })
        if (shut.current) return
        // Jittered backoff, so a server restart does not meet a thundering
        // herd of one.
        const wait = Math.min(MAX_BACKOFF, 250 * 2 ** attempt.current++)
        timer = window.setTimeout(connect, wait * (0.7 + Math.random() * 0.6))
      }
    }

    // A phone backgrounds the tab and the socket dies quietly. Coming back to
    // it should feel instant rather than waiting out the backoff.
    const wake = () => {
      if (
        document.visibilityState === 'visible' &&
        ws.current?.readyState !== WebSocket.OPEN
      ) {
        window.clearTimeout(timer)
        attempt.current = 0
        connect()
      }
    }
    document.addEventListener('visibilitychange', wake)
    window.addEventListener('online', wake)

    connect()
    return () => {
      shut.current = true
      document.removeEventListener('visibilitychange', wake)
      window.removeEventListener('online', wake)
      window.clearTimeout(timer)
      window.clearInterval(beat)
      ws.current?.close()
    }
  }, [dispatch])

  return send
}
