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
| `var/audio/utt-*.wav` | recordings of your room, one per utterance | `RIDDLE_AUDIO_KEEP_DAYS`, 7 by default |
| `var/riddle.db` | every transcript, every stroke, every reply, what each turn cost | until you delete it |
| `var/memories.txt` | the handful of lines the diary chose to keep | until you delete it |
| `var/session` | a Claude Code session id, so the conversation also lives in `~/.claude` | until the page turns |
| `var/backups/rm2-*` | a whole tablet: every notebook, its shell history, **its private ssh keys** | until you delete it |
| `.env` | the tablet's root password | — |

Two caveats about the pruning. `RIDDLE_AUDIO_KEEP_DAYS` is applied **at
startup only**, so a voice server left running for a month never prunes.
And captures are not pruned at all.

## What leaves the machine

- **The rendered page and the transcript window go to Anthropic**, through
  the `claude` CLI, on every turn. The conversation is resumed, so earlier
  pages stay in its context too.
- **The model may search the web.** `WebSearch` and `WebFetch` are allowed
  tools, in character: a diary that has to look something up does not say so.
  So a question written on the page can become a query sent to a search
  engine.
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
rm -f  var/memories.txt var/session  # what it remembered, and the conversation
rm -rf var/backups                   # the tablet snapshots
```

The store is designed to be disposable; nothing else in the project reads it
at startup and expects it to be there.
