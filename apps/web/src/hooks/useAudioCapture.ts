import { useCallback, useRef, useState } from 'react'
import { toast } from 'sonner'

export type CaptureState = 'idle' | 'requesting' | 'recording' | 'stopping'

type Live = {
  ctx: AudioContext
  stream: MediaStream
  node: AudioWorkletNode
  sock: WebSocket
}

/** The microphone, from the button press to the last frame on the wire.
 *
 *  Opening the audio socket is what starts a recording and closing it is what
 *  ends one, so there is no start or stop message that can fall out of step
 *  with what the microphone is actually doing. */
export function useAudioCapture(level: React.RefObject<number>) {
  const live = useRef<Live | null>(null)
  const [state, setState] = useState<CaptureState>('idle')

  const stop = useCallback(async () => {
    const it = live.current
    if (!it) return
    live.current = null
    setState('stopping')
    it.node.port.onmessage = null
    it.node.disconnect()
    // Or ios leaves the orange recording dot lit until the tab is closed.
    it.stream.getTracks().forEach((t) => t.stop())
    // A clean close is the signal to transcribe the tail of what was said.
    it.sock.close(1000, 'done')
    await it.ctx.close()
    level.current = 0
    setState('idle')
  }, [level])

  const start = useCallback(async () => {
    if (live.current) return
    if (!navigator.mediaDevices?.getUserMedia) {
      // This is the insecure-context failure, and it is a TypeError long
      // before any permission prompt. Say so, rather than "mic denied".
      toast.error('No microphone here', {
        description: 'Open this page over https. See ./voice.sh share.',
      })
      return
    }

    setState('requesting')
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 16000,
        },
      })
    } catch (err) {
      setState('idle')
      toast.error('The microphone was refused', { description: String(err) })
      return
    }

    try {
      // Ask for 16 kHz and assume you did not get it. The worklet resamples
      // either way, so this is an optimisation and not a contract.
      let ctx: AudioContext
      try {
        ctx = new AudioContext({ sampleRate: 16000, latencyHint: 'interactive' })
      } catch {
        ctx = new AudioContext({ latencyHint: 'interactive' })
      }
      await ctx.resume() // must happen inside the gesture on ios
      await ctx.audioWorklet.addModule('/pcm-worklet.js')

      const url = new URL('/ws/audio', window.location.href)
      url.protocol = url.protocol.replace('http', 'ws')
      url.search = new URLSearchParams({
        capture: crypto.randomUUID().slice(0, 8),
        rate: '16000',
        frame: '3200',
      }).toString()
      const sock = new WebSocket(url)
      sock.binaryType = 'arraybuffer'
      await new Promise<void>((ok, no) => {
        sock.onopen = () => ok()
        sock.onerror = () => no(new Error('the diary is not listening'))
      })
      sock.onclose = (e) => {
        // Never reconnect a recording. A gap in the audio would be stitched
        // silently into a sentence nobody said.
        if (live.current && e.code !== 1000) {
          toast.error('Recording interrupted')
          void stop()
        }
      }

      const node = new AudioWorkletNode(ctx, 'pcm-worklet', {
        numberOfInputs: 1,
        numberOfOutputs: 0,
        processorOptions: { targetRate: 16000, frameSamples: 3200, levelSamples: 800 },
      })
      node.port.onmessage = (e) => {
        if (e.data.pcm) {
          // Drop rather than queue when the socket is congested: a frame that
          // arrives late is a frame in the wrong sentence.
          if (sock.readyState === WebSocket.OPEN && sock.bufferedAmount < 64 * 1024) {
            sock.send(e.data.pcm)
          }
        } else if (e.data.level !== undefined) {
          level.current = e.data.level // a ref, so the meter costs no render
        }
      }
      // No connect to ctx.destination: routing the microphone to the speakers
      // is feedback.
      ctx.createMediaStreamSource(stream).connect(node)

      live.current = { ctx, stream, node, sock }
      setState('recording')
    } catch (err) {
      stream.getTracks().forEach((t) => t.stop())
      setState('idle')
      toast.error('Could not start listening', { description: String(err) })
    }
  }, [level, stop])

  return { state, start, stop }
}
