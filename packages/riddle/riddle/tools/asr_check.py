"""Check the speech model against a clip of known length.

Run this before trusting a transcript's timing. Two things need settling and
neither is documented: what unit parakeet reports its segment bounds in, and
how long a cold start costs. The answer to the first decides whether a segment
lands on the timeline where it was spoken or a hundred times too late.

    riddle asr check clip.wav

Hand it a clip whose length you know.
"""

import time
import wave
from pathlib import Path


from riddle.voice import ears


def run(args) -> int:
    clip = args.clip
    if not clip.is_file():
        print(f"no clip at {clip}")
        return 1

    with wave.open(str(clip)) as wav:
        seconds = wav.getnframes() / wav.getframerate()
        print(
            f"{clip.name}: {seconds:.2f}s, {wav.getframerate()} Hz, "
            f"{wav.getnchannels()} channel(s)"
        )

    began = time.monotonic()
    segments = ears.transcribe(clip)
    took = time.monotonic() - began

    print(f"\ntranscribed in {took:.1f}s (realtime factor {took / seconds:.2f}x)")
    print("that time includes loading the model, which happens every run.\n")

    if not segments:
        print("no segments came back: check the model path and the clip")
        return 1

    for seg in segments:
        print(f"  [{seg.t0_ms:7d} -> {seg.t1_ms:7d} ms]  {seg.text}")

    last = segments[-1].t1_ms / 1000
    print(f"\nlast segment ends at {last:.2f}s against a clip of {seconds:.2f}s")
    if abs(last - seconds) < seconds * 0.25:
        print(f"units look right: ears.TICK_MS = {ears.TICK_MS} is correct")
        return 0
    print(
        f"units look wrong: change ears.TICK_MS (now {ears.TICK_MS}). "
        f"a ratio of {seconds / max(last, 1e-9):.1f}x is what to correct by"
    )
    return 1
