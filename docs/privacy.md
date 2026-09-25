# What is written down, and what leaves the machine

This project photographs your handwriting, records the room, and sends both
to a model. None of that is hidden, but it is worth being explicit, because
one of those three started happening recently and the other two changed
shape.

## On disk

Everything is under `var/`, which is gitignored whole and can be deleted
entirely without breaking anything that matters.

| where | what it is | how long it stays |
|---|---|---|
| `var/captures/page-*.png` | photographs of what you wrote, rendered from the strokes and sent to the model | **forever** — nothing prunes these yet |
| `var/captures/whole-*.png` | photographs of your **whole page**, read off the tablet's screen, one per turn while `RIDDLE_ALLOW_SNAP=1` | **forever** — nothing prunes these either |
| `var/audio/utt-*.wav` | recordings of your room, one per utterance | `RIDDLE_AUDIO_KEEP_DAYS`, 7 by default |
| `var/riddle.db` | every transcript, every stroke, every reply, what each turn cost | until you delete it |
| `var/memories.txt` | the handful of lines the diary chose to keep | until you delete it |
| `var/chat.json` | the conversation itself: the API keeps none of it, so this is where the thread lives | until the page turns |
| `var/backups/rm2-*` | a whole tablet: every notebook, its shell history, **its private ssh keys** | until you delete it |
| `.env` | the tablet's root password | — |

The page itself keeps three things, in the browser rather than on this
machine, both in `localStorage`:

- `riddle.mic`, the id of the microphone you chose. It is an identifier for
  a device, not a recording.
- `riddle.vanish`, whether the switch on the main page is on.
- `riddle.snapshots`, up to ten **photographs of your whole page**, taken
  with the Snapshot button on `/live`: full-size pngs, exactly the frames the
  live view was sent, with the model's reading of each one you pressed
  Understand on. The server never learns a snapshot was taken. Each
  one can be deleted from the shelf; anyone who can open that browser can
  see them until then.

The microphone and the snapshots never reach the server; the switch does,
because the diary is what obeys it. Clearing the site's data forgets all
three here.

Two caveats about the pruning. `RIDDLE_AUDIO_KEEP_DAYS` is applied **at
startup only**, so a voice server left running for a month never prunes.
And captures are not pruned at all.

The eraser on the page is the exception, and the one thing here that deletes
on purpose: it drops this session's rows from `var/riddle.db` and unlinks
every capture and clip they named. It only ever removes files under `var/`
that a deleted row pointed at, and `var/memories.txt` survives it.

## What leaves the machine

One company, and it is worth knowing what it sees.

- **The photograph of your page goes to OpenAI** on every turn that has ink
  on it, attached to the turn itself. Not a description of it: the image,
  your handwriting as you wrote it. It is cropped to what you wrote since the
  last turn.
- **The transcript window goes with it**, along with the conversation in
  `var/chat.json` -- the words of earlier turns in this thread, though not
  their images, which are never carried forward.
- **The whole page goes too, when the model asks for it and only then.**
  With `RIDDLE_ALLOW_SNAP=1` the diary photographs the entire screen before
  it erases, and offers it as a tool the model may call once per turn. Most
  turns do not call it; the ones that do send a picture of the whole page —
  everything on it, including what you wrote long before this turn and have
  not rubbed out. The photograph is taken whether or not the model asks, and
  is kept on disk either way; what the tool decides is whether it is sent.
  Without that variable set, the diary never reads the screen at all.
- **The diary is one model with one tool**, and the tool only hands back a
  picture of your own page: it searches nothing, fetches nothing, and cannot
  see anything on this machine that a turn did not hand it. The second
  model, below, is only ever asked by a button.
- **The live view sends your whole page to whoever opens it**, about once
  a second, as long as they keep it open. Frames are held in memory and
  never written to disk. Behind the tunnel that is to anybody with the
  password, so the password is guarding your notebook as well as your pen.
  Without `RIDDLE_ALLOW_SNAP=1` it is refused.
- **A snapshot you press Understand on goes to OpenAI**, the whole page,
  to `RIDDLE_UNDERSTAND_MODEL`, and only then. Not kept on this machine; the
  reading comes back to the browser that asked.
- **A document put on the tablet goes to the tablet**, and to nowhere on
  this machine: it is packed in memory and piped into xochitl's store. From
  there it is the tablet's like any other document -- including to
  reMarkable's cloud, if sync is on.
- Nothing else. The server binds loopback; `riddle voice share` exposes it
  only on your own tailnet, behind a certificate.

## The sentence that matters most

**Anything said near the microphone inside a turn's window becomes part of
the question — including other people in the room, who did not press
anything.** A pause turn treats the room as context rather than as the
question, and a send turn uses it directly; either way it is sent.

The microphone is only ever on while you hold the mic button, and the page
says when the gate is open. But the decision about whose voice that is
belongs to you, not to this program.

## Deleting it

```bash
riddle voice stop && riddle diary stop
rm -rf var/audio var/captures        # the recordings and the photographs
rm -f  var/riddle.db*                # the transcripts and the timeline
rm -f  var/memories.txt var/session var/chat.json  # what it remembered, and the conversation
rm -rf var/backups                   # the tablet snapshots
```

The store is designed to be disposable; nothing else in the project reads it
at startup and expects it to be there.

The eraser on the page does the same thing for one session without stopping
anything: the diary rubs its ink off the page, drops the conversation, and
deletes that session's rows along with every capture and clip they named.
`var/memories.txt` is what survives it, on purpose.
