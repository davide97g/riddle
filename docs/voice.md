# The page you speak into

`riddle voice start`, then open it on your phone. It records what is said,
transcribes it, shows a timeline of everything that happened, and asks the
diary for an answer when you press Send.

It **never opens an ssh connection and never draws**. The loop owns the pen;
this half leaves a note in the store and the loop picks it up. That is why
there is no lock anywhere in it and no second `Device`.

## Why it is a separate process

The loop blocks for seconds at a time driving the pen — an erase pass over a
page of handwriting is not quick — and it owns the one ssh pipe to the
tablet. A web server cannot live inside that. The two halves share a file,
not a device.

## What you need

**`parakeet-cli` on your PATH.** A ggml binary that takes a file and prints
its segments. Check with `parakeet-cli --help`.

**The model**, about 640 MB, fetched once by hand into
`var/models/ggml-parakeet-tdt-0.6b-v3-q8_0.bin`. `RIDDLE_ASR_MODEL` points
somewhere else; a relative path hangs off `var/models`. Without it the server
still starts, the mic button is disabled and the page says why —
`riddle asr model` tells you where it is looking.

**The client built**: `riddle web install && riddle web build`. Without it
the server serves a stub page that says so, and the API still works.

numpy, which the venv already has.

## Reaching it from a phone

This is the step that fails silently, so it is worth being exact.

A browser will not hand a page the microphone unless it is a **secure
context**. `http://192.168.1.x:8765` is not one. It is not a warning, and it
is not a permission prompt you can accept: `navigator.mediaDevices` is simply
not there, and the failure arrives as a `TypeError` before anything asks you
about a microphone.

So the server binds loopback only, deliberately, and:

```
riddle voice share      # tailscale serve --bg 8765, and prints the https url
riddle voice unshare
```

Tailscale holds a real certificate for this machine's tailnet name and
proxies it to loopback, which is why nothing here has to grow an ssl import
and why the bind address should stay `127.0.0.1`. `share` refuses when
nothing is listening on the port, because a certificate in front of a dead
port shows the phone a 502 and sends you to debug the wrong layer.

For development: `riddle web dev --tailnet`, or `riddle dev --tailnet` for
that dev server and both halves at once. Hot reload has to dial 443 over
`wss` because tailscale terminates the TLS, and `RIDDLE_SERVER` points the
proxy at the Python server.

## How the listening works

There is no VAD model. `whisper-vad-speech-segments` exists but wants a
silero model that is not downloaded, reads files rather than a stream, and
would add a second model load per utterance. Twenty lines of numpy is
cheaper and the failure mode — a cut in the wrong place — is the same either
way.

Per 20 ms frame, at 16 kHz mono:

- RMS against an adaptive floor: three times the 10th percentile of the last
  three seconds, or `RIDDLE_VAD_FLOOR`, whichever is higher;
- **open** after three consecutive loud frames, because a chair creak and a
  keyboard click each clear the gate for exactly one;
- **close** after `RIDDLE_VAD_HANG_MS` of quiet, or at `RIDDLE_VAD_MAX_MS`
  when somebody is monologuing;
- 300 ms of pre-gate audio is prepended, so an utterance does not lose the
  consonant that started it.

Then the clip is written to `var/audio/utt-*.wav` and transcribed **once**.
`parakeet-cli` cannot stream and reloads six hundred megabytes on every
invocation, so there is no such thing as a partial transcript and no point
pretending otherwise. Runs are serialised: two of them share one Metal
context and make each other slower for no gain.

**Each segment lands on the timeline by when it was spoken, not by when the
model finished.** That is the single most important sentence in this file. It
is why the page sorts rows by `t_ms` rather than by arrival, and why the loop
waits a moment before closing a turn's window.

### Tuning

| symptom | knob |
|---|---|
| the fridge is being transcribed | raise `RIDDLE_VAD_FLOOR` |
| quiet speech is missed | lower it |
| sentences are cut mid-clause | raise `RIDDLE_VAD_HANG_MS` |
| one long utterance never ends | lower `RIDDLE_VAD_MAX_MS` |
| transcription is slow | `RIDDLE_ASR_THREADS` |
| transcripts land in the wrong place on the timeline | `riddle asr check <clip.wav>` |

`riddle asr check` times a cold run and verifies the unit parakeet reports
its segment bounds in — which decides whether a sentence lands where it was
spoken or a hundred times too late.

## The page

Rows are the timeline, in the order things happened: what you wrote, what was
said, what the diary answered, what it is doing, what went wrong. Press Send
to ask for an answer now; the answer always appears on the tablet, and the
row is only the record of it.

Send is disabled when the diary is not running, because nothing would answer
it. The mic button is disabled when there is no speech model.

Under the level meter is **which microphone is listened to**. A browser lists
no inputs at all until it has granted one, so before the first recording the
control is a *Choose microphone* button: pressing it opens the default input
for as long as it takes to learn the names, then lets go. The choice is kept
in the browser, per browser, and used for every recording after it. It cannot
be changed while a recording is running, because two inputs spliced into one
sentence is worse than the wrong one throughout.

A microphone that is chosen and then unplugged falls back to the system
default at the next press, and says so rather than refusing to listen.

This is worth checking first when nothing is transcribed: a recording from a
silent input reaches the server, is gated as silence and produces no
utterance at all, which looks exactly like a broken model.

## What is written down

`var/audio/*.wav` are recordings of your room, pruned after
`RIDDLE_AUDIO_KEEP_DAYS` (7 by default, at startup only). Transcripts live in
the store. See [privacy.md](privacy.md), and read it before you leave this
running in a room with other people in it.

## When it will not work

| what you see | why |
|---|---|
| mic button disabled | no speech model, or the diary is offline, or the socket is closed |
| the meter never moves, and nothing is transcribed | a silent input is selected: pick another under the meter |
| a TypeError about mediaDevices | not a secure context: `riddle voice share` |
| the page says it has not been built | `riddle web build` |
| Send does nothing | the loop is not running; the intent waits, and expires after two minutes |
| `parakeet failed` | check `parakeet-cli --help` and the model path |
| transcripts in the wrong place | `riddle asr check` against a clip of known length |
