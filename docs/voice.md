# The page you speak into

`riddle voice start`, then open it on your phone. It records what is said,
transcribes it, shows a timeline of everything that happened, and asks the
diary for an answer when you press Send.

It **never opens the pen's pipe and never draws**. The loop owns the pen;
this half leaves a note in the store and the loop picks it up. That is why
there is no lock anywhere in it and no second `Device`. Its one ssh
connection is the live view's, which only ever reads the screen, and only
while a page is watching it.

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

## The password

`RIDDLE_WEB_PASSWORD` puts one password in front of the whole page. Unset, as
it is by default, there is no gate at all -- right for `127.0.0.1`, where
reaching the port already means reaching the machine, and wrong the moment
the port is published to anything. The mechanics are in
[protocols.md](protocols.md#the-gate); what matters here is that the page can
make the pen write, so whoever reaches it is writing in your notebook.

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

## Watching the page live

`/live` is a page of its own: the page on the tablet, as it is right now,
about once a second. The eye in the header goes there. There is no model in
it and nothing is drawn back: you write on the tablet and the phone shows
it. It has no control that reaches the pen, so it can be left open on a
second screen or handed to somebody who should see the notebook without
being able to send, erase or stop anything. It needs
`RIDDLE_ALLOW_SNAP=1` on the server, because it reads the screen the way
`riddle snap` does, and without it the eye is disabled and says why. It
does **not** need the diary running — the feed is its own ssh connection,
so it keeps going while the loop is stopped, or busy drawing an answer.

It opens no events socket, only `/ws/live`, and leaving it is what ends the
feed.

**Snapshot** takes the frame on screen: it goes onto the clipboard as a png
and onto the shelf beside the page (under it on a phone), which keeps the
last ten in the browser's `localStorage` and survives a reload. Each one
opens full size and downloads or copies on its own, as the tablet sent it —
1404x1872, white paper, black ink — whatever the dark theme did to the
preview. Nothing is read off the tablet again for it, and the server never
hears about it. A browser whose storage is full keeps as many of the newest
as fit and says so. Safari and Chrome copy images; a browser that cannot
still keeps the snapshot and says it did not copy. Only frames that changed are sent, so the line above the page says when it
last changed rather than when it was last read. A frame is a torn read:
the stroke being drawn as it is taken can come out half finished, and is
whole in the next one. The wire is in
[protocols.md](protocols.md#wslive--the-tablets-screen-outbound-only) and
the tablet's side in [device.md](device.md#reading-the-screen).

## Putting a document on the tablet

The file button in the header of both pages -- or a file dropped anywhere on
either -- puts a pdf, an epub or an image in the tablet's library as a real
document, rendered by xochitl itself rather than traced by the pen: sharp at
every zoom, and a page you can write on. An image becomes a one-page pdf in
greys; the rest goes in as it is. The dialog takes a name for the library,
the file's own by default.

It asks every time because the way in is **a restart of xochitl**: whatever
is open closes, the screen reloads for about ten seconds, and if the diary
was halfway through a word the word stops. Then open the document from the
library; nothing here can open it for you. It does not need the diary, and
on `/live` you can watch the tablet come back. How the store is written is in
[device.md](device.md#putting-a-document-in-the-library).

## What is written down

`var/audio/*.wav` are recordings of your room, pruned after
`RIDDLE_AUDIO_KEEP_DAYS` (7 by default, at startup only). Transcripts live in
the store. See [privacy.md](privacy.md), and read it before you leave this
running in a room with other people in it.

## When it will not work

| what you see | why |
|---|---|
| mic button disabled | no speech model, or the diary is offline, or the socket is closed |
| the eye is disabled | `RIDDLE_ALLOW_SNAP` is not set on the server |
| the live view says it lost the tablet | the tablet is asleep or off the network; it redials by itself |
| the meter never moves, and nothing is transcribed | a silent input is selected: pick another under the meter |
| a TypeError about mediaDevices | not a secure context: `riddle voice share` |
| the page says it has not been built | `riddle web build` |
| Send does nothing | the loop is not running; the intent waits, and expires after two minutes |
| `parakeet failed` | check `parakeet-cli --help` and the model path |
| transcripts in the wrong place | `riddle asr check` against a clip of known length |
