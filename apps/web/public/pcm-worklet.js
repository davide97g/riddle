// Downsample to 16 kHz, pack to int16, hand up 200 ms frames.
//
// This is a worklet and not a ScriptProcessorNode because the render quantum
// runs on the audio thread: a react re-render, a websocket send or a garbage
// collection on the main thread cannot drop samples here.

const QUANTUM = 128

class PCMWorklet extends AudioWorkletProcessor {
  constructor(options) {
    super()
    const {
      targetRate = 16000,
      frameSamples = 3200,
      levelSamples = 800,
    } = options.processorOptions || {}

    this.ratio = sampleRate / targetRate // `sampleRate` is a worklet global
    this.pos = 0 // fractional read cursor, carried across render quanta
    this.prev = 0 // last input sample of the previous quantum
    this.lp = 0 // one-pole anti-alias state
    // A gentle low pass ahead of decimation. It is not a good filter, but
    // speech above 8 kHz carries nothing the model wants, and what aliases
    // through sits under the noise floor of any microphone a person owns.
    this.alpha = Math.min(1, targetRate / sampleRate)

    this.work = new Float32Array(QUANTUM)
    this.frame = new Int16Array(frameSamples)
    this.frameSamples = frameSamples
    this.n = 0
    this.seq = 0

    this.levelSamples = levelSamples // ~50 ms, so the meter moves at 20 fps
    this.levelN = 0
    this.sumsq = 0
    this.peak = 0
  }

  process(inputs) {
    const chan = inputs[0] && inputs[0][0]
    if (!chan) return true // muted, or the stream has not started; stay alive

    // Filter into scratch. The input arrays belong to the engine and may be
    // recycled, so nothing is written back through them.
    const work = this.work
    for (let i = 0; i < chan.length; i++) {
      this.lp += this.alpha * (chan[i] - this.lp)
      work[i] = this.lp
    }

    while (this.pos < chan.length) {
      const i = this.pos | 0
      const f = this.pos - i
      const a = i === 0 ? this.prev : work[i - 1]
      const s = a + (work[i] - a) * f
      const v = s < -1 ? -1 : s > 1 ? 1 : s

      this.frame[this.n++] = v < 0 ? v * 0x8000 : v * 0x7fff

      this.sumsq += v * v
      const m = v < 0 ? -v : v
      if (m > this.peak) this.peak = m

      if (++this.levelN === this.levelSamples) {
        this.port.postMessage({
          level: Math.sqrt(this.sumsq / this.levelN),
          peak: this.peak,
        })
        this.levelN = 0
        this.sumsq = 0
        this.peak = 0
      }

      if (this.n === this.frameSamples) {
        // Four byte little-endian frame index, then int16le pcm. The index is
        // what lets a sentence be placed by where it was spoken rather than
        // by where it happened to arrive.
        const out = new ArrayBuffer(4 + this.frameSamples * 2)
        new DataView(out).setUint32(0, this.seq++, true)
        new Int16Array(out, 4).set(this.frame)
        this.port.postMessage({ pcm: out }, [out]) // transferred, not copied
        this.n = 0
      }

      this.pos += this.ratio
    }

    // 48000/16000 is a clean 3, but a bluetooth headset gives 44100 and that
    // is 2.75625. Carrying the fractional remainder across the quantum is
    // what keeps the resampler in phase; snapping to the boundary instead
    // adds a periodic artefact right in the speech band.
    this.pos -= chan.length
    this.prev = work[chan.length - 1]
    return true
  }
}

registerProcessor('pcm-worklet', PCMWorklet)
