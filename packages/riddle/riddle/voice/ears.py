"""Listening: raw microphone frames in, sentences with timestamps out.

The model here is `parakeet-cli`, a ggml binary that takes a file and prints
its segments. That shapes everything: it cannot stream, and it reloads six
hundred megabytes on every invocation, so there is no such thing as a partial
transcript and there is no point pretending otherwise. What there is instead
is a cut: decide where an utterance ended, write that much audio to a wav, and
transcribe it once.

Deciding where it ended is the whole job, and it is done with an energy gate
rather than a model. `whisper-vad-speech-segments` exists on this machine but
wants a silero model that is not downloaded, reads files rather than a stream,
and would add a second load per utterance. Twenty lines of numpy is cheaper
and the failure mode -- a cut in the wrong place -- is the same either way.
"""

import asyncio
import os
import re
import subprocess
import sys
import time
import wave

from riddle import paths
from dataclasses import dataclass
from pathlib import Path

import numpy as np

RATE = 16000
FRAME_MS = 20
FRAME = RATE * FRAME_MS // 1000  # 320 samples

# The format string pulled straight out of the binary:
#   "Segment %d: [%lld -> %lld] \"%s\""
SEGMENT = re.compile(r'^Segment\s+\d+:\s+\[(-?\d+)\s*->\s*(-?\d+)\]\s+"(.*)"\s*$')

# What one unit of those bounds is worth in milliseconds. whisper reports
# centiseconds and parakeet mirrors its api, so this is 10 until
# host/tools/asr_check.py says otherwise against a clip of known length.
TICK_MS = 10


@dataclass
class Segment:
    t0_ms: int
    t1_ms: int
    text: str


def model_path() -> Path:
    """Where the speech model is. Relative paths hang off var/models."""
    name = os.environ.get("RIDDLE_ASR_MODEL", "ggml-parakeet-tdt-0.6b-v3-q8_0.bin")
    return paths.under_root(name, paths.MODELS)


def transcribe(clip: Path, timeout: int = 180) -> list[Segment]:
    """Run the model over one file. Blocking, and slow enough to matter."""
    model = model_path()
    if not model.is_file():
        raise RuntimeError(f"no speech model at {model}")

    done = subprocess.run(
        [
            "parakeet-cli",
            "-m", str(model),
            "-f", str(clip),
            "-ps", "-np",
            "-t", os.environ.get("RIDDLE_ASR_THREADS", "4"),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if done.returncode != 0:
        tail = done.stderr.strip().splitlines()
        raise RuntimeError(tail[-1] if tail else "parakeet failed")

    # The segments go to stderr, not stdout. stdout carries only the plain
    # transcript, and -np does not quiet the backend chatter either, so both
    # streams are scanned and anything that is not a segment is ignored.
    segments = []
    for line in (done.stdout + done.stderr).splitlines():
        found = SEGMENT.match(line.strip())
        if not found:
            continue
        t0, t1, text = found.groups()
        text = " ".join(text.split())
        if text:
            segments.append(Segment(int(t0) * TICK_MS, int(t1) * TICK_MS, text))
    return segments


class Gate:
    """Where speech starts and stops, by loudness alone.

    The floor adapts, because a quiet room at night and a kitchen at noon are
    twenty decibels apart and a fixed threshold gets one of them wrong.
    """

    def __init__(self) -> None:
        self.floor = float(os.environ.get("RIDDLE_VAD_FLOOR", "0.012"))
        self.hang_ms = int(os.environ.get("RIDDLE_VAD_HANG_MS", "700"))
        self.max_ms = int(os.environ.get("RIDDLE_VAD_MAX_MS", "20000"))
        self.history: list[float] = []
        self.loud = 0      # consecutive frames over the gate
        self.quiet_ms = 0
        self.speaking = False

    def feed(self, frame: np.ndarray) -> tuple[bool, float]:
        """Take one 20ms frame; say whether we are inside speech, and how loud."""
        rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)) / 32768.0)
        self.history.append(rms)
        if len(self.history) > 3000 // FRAME_MS:  # three seconds
            self.history.pop(0)
        noise = float(np.percentile(self.history, 10)) if len(self.history) > 10 else 0.0

        over = rms > max(noise * 3.0, self.floor)
        if over:
            self.loud += 1
            self.quiet_ms = 0
        else:
            self.loud = 0
            self.quiet_ms += FRAME_MS

        if not self.speaking:
            # Three frames, not one: a chair creak and a keyboard click both
            # clear the gate for a single frame.
            if self.loud >= 3:
                self.speaking = True
        elif self.quiet_ms >= self.hang_ms:
            self.speaking = False
        return self.speaking, rms


class Capture:
    """One press of the microphone button."""

    def __init__(self, ears: "Ears", name: str) -> None:
        self.ears = ears
        self.name = re.sub(r"[^A-Za-z0-9_-]", "", name)[:40] or str(int(time.time()))
        self.began_ms = ears.store.now_ms()
        self.gate = Gate()
        self.next_seq = 0
        self.pending = np.zeros(0, dtype=np.int16)   # samples not yet gated
        self.utterance: list[np.ndarray] = []
        self.utterance_ms = 0
        # How far into the recording we have listened. Every frame advances
        # it, speech or not, because this is what says where a sentence sits
        # on the timeline -- not how long the sentence itself ran.
        self.elapsed_ms = 0
        # A few frames of what came before the gate opened, so an utterance
        # does not lose the consonant that started it.
        self.preroll: list[np.ndarray] = []
        self.spoke = 0
        self.tasks: set[asyncio.Task] = set()

    async def feed(self, seq: int, pcm: bytes) -> None:
        samples = np.frombuffer(pcm, dtype="<i2")
        if seq > self.next_seq:
            # The page drops a frame rather than queue it when the socket is
            # congested, so a gap is real silence in the room's timeline, not
            # something to paper over by shifting everything later.
            missing = (seq - self.next_seq) * len(samples)
            self.pending = np.concatenate(
                [self.pending, np.zeros(min(missing, RATE * 5), dtype=np.int16)]
            )
        self.next_seq = seq + 1
        self.pending = np.concatenate([self.pending, samples])
        await self._gate()

    async def _gate(self) -> None:
        while len(self.pending) >= FRAME:
            frame, self.pending = self.pending[:FRAME], self.pending[FRAME:]
            speaking, _level = self.gate.feed(frame)

            self.elapsed_ms += FRAME_MS

            if speaking:
                if not self.utterance:
                    self.utterance = list(self.preroll)
                    self.utterance_ms = len(self.preroll) * FRAME_MS
                    await self.ears.say({"type": "hearing", "on": True})
                self.utterance.append(frame)
                self.utterance_ms += FRAME_MS
            else:
                self.preroll.append(frame)
                if len(self.preroll) > 300 // FRAME_MS:
                    self.preroll.pop(0)
                if self.utterance:
                    await self.cut()

            if self.utterance and self.utterance_ms >= self.gate.max_ms:
                # Somebody is monologuing. Cut anyway, or the first sentence
                # does not land until the last one is finished.
                await self.cut()

    async def cut(self) -> None:
        """End the utterance and send it off to be read."""
        if not self.utterance:
            return
        audio = np.concatenate(self.utterance)
        # Where this sentence began: how far we have listened, less how long
        # the sentence itself was.
        started = self.began_ms + max(0, self.elapsed_ms - len(audio) * 1000 // RATE)
        self.utterance = []
        self.utterance_ms = 0
        self.preroll = []
        self.gate.speaking = False
        await self.ears.say({"type": "hearing", "on": False})

        self.spoke += 1
        path = self.ears.audio_dir / f"utt-{self.name}-{self.spoke:04d}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(RATE)
            wav.writeframes(audio.tobytes())

        task = asyncio.create_task(self.ears.read(path, started))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def done(self) -> None:
        """The page stopped sending. Take whatever is left as a last sentence."""
        await self._gate()
        if self.utterance:
            await self.cut()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)


class Ears:
    def __init__(self, store, root: Path) -> None:
        self.store = store
        self.root = root
        self.audio_dir = root / "audio"
        self.hub = None
        # One at a time. Two parakeet processes share one Metal context and
        # make each other slower for no gain.
        self.one_at_a_time = asyncio.Semaphore(1)

    async def say(self, message: dict) -> None:
        if self.hub is not None:
            await self.hub.say(message)

    def begin(self, name: str) -> Capture:
        return Capture(self, name)

    async def read(self, clip: Path, started_ms: int) -> None:
        # There is no partial transcript to show, so the page is told that a
        # sentence is being read and holds a placeholder until it lands.
        await self.say({"type": "pending", "clip": clip.name, "on": True})
        try:
            async with self.one_at_a_time:
                segments = await asyncio.to_thread(transcribe, clip)

            keep = str(clip.relative_to(self.root))
            for seg in segments:
                # Placed by when it was said, not by when the model finished.
                # The model lags by seconds and the timeline is meant to show
                # the room, not the queue.
                self.store.add_event(
                    "speech",
                    t_ms=started_ms + seg.t0_ms,
                    dur_ms=max(0, seg.t1_ms - seg.t0_ms),
                    text=seg.text,
                    path=keep,
                    meta={"clip": clip.name},
                )
            if not segments:
                clip.unlink(missing_ok=True)
        except Exception as exc:
            print(f"could not read {clip.name}: {exc}", file=sys.stderr)
            await self.say({"type": "error", "message": f"could not hear that: {exc}"})
        finally:
            await self.say({"type": "pending", "clip": clip.name, "on": False})

    def prune(self) -> None:
        """Drop old recordings.

        These are kept so a transcript can be checked against what was
        actually said, or re-run against a better model. They are also a
        recording of your room, so they do not stay forever.
        """
        days = int(os.environ.get("RIDDLE_AUDIO_KEEP_DAYS", "7"))
        if days <= 0 or not self.audio_dir.is_dir():
            return
        cutoff = time.time() - days * 86400
        gone = 0
        for clip in self.audio_dir.glob("utt-*.wav"):
            if clip.stat().st_mtime < cutoff:
                clip.unlink(missing_ok=True)
                gone += 1
        if gone:
            print(f"pruned {gone} recording(s) older than {days} days", file=sys.stderr)
