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
| `var/chat.json` | the conversation itself, when the mind is DeepSeek: it keeps nothing, so this is where the thread lives | until the page turns |
| `var/backups/rm2-*` | a whole tablet: every notebook, its shell history, **its private ssh keys** | until you delete it |
| `.env` | the tablet's root password | — |

The page itself keeps one thing, in the browser rather than on this machine:
`riddle.mic`, in `localStorage`, the id of the microphone you chose. It is an
identifier for a device, not a recording, it never reaches the server, and
clearing the site's data forgets it.

Two caveats about the pruning. `RIDDLE_AUDIO_KEEP_DAYS` is applied **at
startup only**, so a voice server left running for a month never prunes.
And captures are not pruned at all.

The eraser on the page is the exception, and the one thing here that deletes
on purpose: it drops this session's rows from `var/riddle.db` and unlinks
every capture and clip they named. It only ever removes files under `var/`
that a deleted row pointed at, and `var/memories.txt` survives it.

## What leaves the machine

Two companies, by default, and it is worth knowing which sees what.

- **The rendered page goes to Anthropic**, through the `claude` CLI, on every
  turn that has ink on it. `RIDDLE_EYES_MODEL` reads it and describes what is
  written and drawn there; that call sees the photograph itself.
- **That description, and the transcript window, go to DeepSeek**, which
  writes the reply. It never sees the image, and the conversation it is sent
  is the one in `var/chat.json`, so earlier pages' descriptions go with it.
  DeepSeek is a Chinese company and its API terms are its own; if that is not
  a thing you want, `RIDDLE_MIND=claude` is one line in `.env`.
- **With `RIDDLE_MIND=claude`, only Anthropic sees any of it**, and the model
  may then search the web: `WebSearch` and `WebFetch` are allowed tools, in
  character, so a question written on the page can become a query sent to a
  search engine. The DeepSeek mind has no tools and searches nothing.
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
