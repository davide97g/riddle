# The drawing half

`riddle diary start`. It owns the ssh pipe to the tablet and is the only
thing in the project that moves the pen.

## What counts as a question

A pause on its own is not a question. Nearly everything you do to a tablet
arrives as pen input, and none of it is something to answer: pressing a tool
in the toolbar, poking the page awake, rubbing something out, leaving a blot
while you think.

So a stroke is thrown away when it is

- **a press** — under `TAP_TRAVEL` (25 px) of actual travel;
- **inside the toolbar strip** — entirely left of `TOOLBAR_X` (110 px), which
  catches a drag on the thickness slider;
- **an eraser pass** — which instead deletes the pending strokes it crosses,
  within `ERASE_RADIUS` (28 px).

And a turn only fires when what is left is `MIN_INK` (500 px) of travel
spanning `MIN_SPAN` (110 px) of bounding box. A dot and a comma are quiet,
not a question.

The nib/eraser distinction comes from the agent's `K PEN|RUBBER` line, which
is the real `BTN_TOOL_*` bit. A *UI-selected* eraser used with the nib is
indistinguishable from writing at the evdev layer and still reads as ink.

A finger only pushes the clock back: handling the tablet is not writing.

And the pause is measured from a **pen lift**, not from silence — a nib
resting on the page emits nothing at all, because the input core drops
repeated coordinates.

## When the diary keeps its hands off

Three things turn a pause back into only a pause, all asked for by a page
and all read at the moment a turn would start:

- **The switch is off.** "Vanish and answer" on the main page, kept in the
  store as `diary.vanish`. Off, nothing fades and nothing is written back:
  the page is for notes that are meant to stay.
- **Somebody is watching the tablet live.** While `/live` is open the voice
  server refreshes `live.watching` every five seconds, and the loop treats a
  beat younger than fifteen seconds as a person looking at the page -- which
  the diary must not rub out underneath them. A beat rather than a flag, so
  a voice server that dies with a page open cannot stop the diary for good.
- **Somebody is sharing a screen with the tablet.** While `/share` has a
  screen up it sends a `share` beat every five seconds, kept as
  `share.watching` and read the same way: the page is somebody's slide, and
  what is written on it is for them. The same beat is what makes the loop
  send each stroke back as an `ink` event as it ends -- see
  [voice.md](voice.md#sharing-a-screen-with-the-tablet).

A pause sat out this way **lets the strokes go** rather than keeping them for
later: kept, they would be erased by the next turn that did happen, which is
exactly the writing that was meant to stay. They are not the diary's ink
either, so the eraser on the page leaves them alone. A Send in either state
is refused with the reason, as an `error` row, rather than answered on top of
writing that is staying.

## A turn

```
pen up ── pause ── photograph ──┬─ erase the page  (device, seconds) ─┐
                  (1-2s, opt.)  └─ wait for speech (≤2.5s, cap 6s) ───┴─ model ─ draw
```

The erase and the wait happen at the same time, and that is the nicest
property of the design: **the grace period costs nothing, because it hides
inside the erase.** The ink starts fading the moment you stop writing, which
is the point; and by the time the page is clear, a sentence that was still
inside the speech model has landed.

"Wait for speech" means: until nothing new has been transcribed for 750 ms
*and* no clip is with the model. The loop learns the second from
`state.asr.inflight`, which the voice half writes. With no voice server
running, the wait is skipped entirely.

Then the window closes, the turn claims everything spoken and typed inside
it, and the question goes out:

| trigger | ink | what is sent |
|---|---|---|
| pause | always | the writing, plus any transcript **as context**: *"answer what the page says; the room is only context"* |
| send | yes | the writing, the transcript and the draft |
| send | no | the transcript and the draft, **and no image at all** |
| send | nothing at all | refused, with an `error` event |

"The writing" is exactly that: the strokes since the last turn, rendered and
cropped to their own bounding box. The rest of the page is a separate thing,
below.

The last two rows matter. The persona says the image is a photograph of
their handwriting; feeding it a blank page is a lie, and the model answers it
by inventing something. And because the conversation is *resumed*, a turn
with no image has to say so explicitly, or the model answers from the last
page it saw.

The reply is recorded before the pen moves, so the phone shows the answer
while the tablet is still inking it. Then the diary selects the pen and
writes, centred on the space the writing occupied.

If the model returns nothing, the original strokes are drawn back rather than
leaving a blank page where the question was.

## The rest of the page

What a turn carries is the new writing and nothing else. That is the
question, and for most turns it is the whole of it. It is also cropped, so
what the model never sees is everything the page already held: the line being
corrected, the diagram being added to, whatever an arrow points at, the
diary's own last reply still sitting there in a different hand.

So with `RIDDLE_ALLOW_SNAP=1` the loop photographs the whole screen once per
turn and offers it to the model as a tool, `look_at_page`, which most turns
never call. Offered rather than attached, because a full-page image on every
turn costs tokens and seconds on every turn to be useful on one in five.

Three things about the timing, all of them forced:

- **It happens before the eraser**, and that is the only place it can. A
  moment later the writing is fading off the page and the photograph is of a
  page being wiped.
- **So the ink starts fading a second or two later than it otherwise would.**
  That is the price of the feature, and it is why the feature is off by
  default. The read is ten megabytes out of xochitl's address space over ssh,
  gzipped on the tablet to about 36KB.
- **A tablet that does not answer in 12 seconds costs the turn its context,
  not the turn.** The photograph is skipped, the tool is not offered, and the
  turn goes on.

The loop also says when it can tell the crop is lying. It knows where its
own ink is and where this turn's strokes are, so strokes that land on top of
ink already on the page -- a circle drawn around the diary's last reply, an
arrow reaching back into it -- are arithmetic, not a guess, and the turn says
so in as many words. That is the one case the cropped photograph is actively
misleading about: the circle arrives enclosing nothing, and a model that
answers what it sees will say the circle is empty.

The look is capped at one per turn: the page does not change while the turn
runs, so a second look would photograph nothing new. When it happens, a
`tool` row says so — `meta.doing` is `looking at the whole page` — and the
photograph itself is a `shot` row with a path, which the page renders.

Reading the screen is a different capability from drawing on it, and the two
switches stay separate: `RIDDLE_ALLOW_SNAP` is the one `riddle snap` answers
to, and the loop answers to it too rather than inventing a third. Without it
the loop never reads the screen, and says so at startup.

## Select the pen first

An injected stroke becomes whatever tool xochitl has active. With the lasso
selected, a page of handwriting silently becomes a page of *selections*. It
looks exactly like a rendering bug and is not one.

The taps that press the pen button live in `taps.json` and are re-recorded
with `riddle taps learn pen --yes`. `riddle doctor` asserts one exists,
because this failure prints nothing.

## Being asked from the page

Between pen events the loop drains `intents`: never while the nib is down,
never mid-turn, a few times a second, and behind a cheap indexed read so an
empty queue never takes the write lock the voice half is using.

`send` answers now. `forget` drops the conversation. `draw`, `erase` and
`shot` are recognised and refused with a reason — a row is never left
running, and "unknown action" is not an answer. Duplicate sends collapse into
one turn, because double-tapping a button on a phone is inevitable.

## Forgetting, and what survives it

Turning to a new page, opening another notebook or clearing the page ends the
conversation: the resumed session id is dropped and the next turn starts
clean.

What does not go is `var/memories.txt`. The model ends a reply with
`REMEMBER: <one line>` when something should outlive the reset, and that line
is stripped before it can reach the page. It is a plain file on purpose: it
outlives the store, whose schema keeps changing and which is safe to delete.
Each kept line is also mirrored onto the timeline as a note, so the page can
show that the diary chose to remember something.

Two things constrain how well this works. xochitl only flushes a page when
you navigate away from it, so a clear is noticed shortly after the fact
rather than as it happens. And the diary's own answering — erase the page,
write over it — looks exactly like the writer wiping it, which would make it
forget after every sentence; the watcher is held off while answering and
re-baselines instead.
