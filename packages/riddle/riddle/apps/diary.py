#!/usr/bin/env python3
"""Tom Riddle diary for the reMarkable 2.

Write on a page. Pause. What you wrote fades off the page and the diary
answers you in ink, in its own hand.

This half owns the ssh pipe to the tablet, and it is the only thing that
moves the pen. The other half -- the page you speak into -- cannot reach the
device at all; it leaves a note in the store and this loop picks it up.
"""

import queue
import sys
import threading
import time

from riddle import config, paths
from riddle.device import Device, PenUp, Sample, Tool, Touch, notebook, pages
from riddle.ink import hershey, render
from riddle.ink.geometry import SCREEN_H, SCREEN_W
from riddle.ink.style import Palette
from riddle.mind.llm import Diary, Question
from riddle.mind.memory import Memory
from riddle.store import Store

PAGE_MARGIN = 70

# What counts as writing, and what is only handling the tablet. Every one of
# these arrives as pen input and none of them is a question: pressing a tool in
# the toolbar, poking the page awake, rubbing something out, leaving a blot.
TOOLBAR_X = 110       # screen px: a stroke wholly inside the left strip is UI
TAP_TRAVEL = 25       # px of travel below which a stroke is a press, not a mark
MIN_INK = 500         # px of travel before the page holds anything to answer
MIN_SPAN = 110        # px of bounding box: a word is wider than a dot
ERASE_RADIUS = 28     # px: an eraser pass this close takes the stroke with it

BEAT_S = 5.0          # how often the loop says it is still here
PUMP_S = 0.25         # how often intents are looked for, matching the page's poll
INTENT_TTL_MS = 120_000    # a send nobody served in two minutes is stale
SPEECH_GRACE_MS = 2_500    # how long to wait for a sentence still being transcribed
SPEECH_GRACE_CAP_MS = 6_000
SPEECH_QUIET_MS = 750      # no new transcript for this long means it has landed
SEND_LOOKBACK_MS = 120_000
ORPHAN_MS = 30_000    # how far back a turn reaches for input written late


def travel(stroke: list[tuple[float, float]]) -> float:
    """How far the nib actually moved along a stroke."""
    return sum(
        ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        for a, b in zip(stroke, stroke[1:])
    )


def crosses(stroke, pass_, radius: float) -> bool:
    """Whether an eraser pass went over a stroke."""
    sx = [x for x, _ in stroke]
    sy = [y for _, y in stroke]
    px = [x for x, _ in pass_]
    py = [y for _, y in pass_]
    if (
        min(sx) - radius > max(px)
        or max(sx) + radius < min(px)
        or min(sy) - radius > max(py)
        or max(sy) + radius < min(py)
    ):
        return False
    # Both sides are sampled far finer than the radius, so stepping over them
    # keeps this cheap without letting a pass slip between two points.
    near = radius * radius
    for ex, ey in pass_[::3]:
        for x, y in stroke[::3]:
            if (x - ex) ** 2 + (y - ey) ** 2 <= near:
                return True
    return False


class NoStore:
    """What the loop talks to when there is no usable store.

    The diary worked before it kept any record of itself, and a locked or
    corrupt sqlite file must not be a reason the tablet stops answering. So
    every store call goes through a handle that may quietly be this instead.
    """

    session_id = 0
    role = "loop"

    def __init__(self) -> None:
        self.started_ms = int(time.time() * 1000)

    def now_ms(self) -> int:
        return int(time.time() * 1000) - self.started_ms

    def __getattr__(self, name):
        def nothing(*args, **kwargs):
            return None

        return nothing


class Session:
    def __init__(self) -> None:
        cfg = config.get()
        self.cfg = cfg
        self.pause_s = cfg.pause_ms / 1000
        self.ink_height = float(cfg.ink_height)
        self.pressure = cfg.pressure
        self.palette = Palette(body=cfg.font_body, accent=cfg.font_accent)
        self.store = self._open_store()
        self.memory = Memory(paths.MEMORIES, on_keep=self._remembered)
        self.diary = Diary(
            model=cfg.model,
            max_words=cfg.max_words,
            session_file=paths.SESSION,
            memory=self.memory,
        )
        self.device = Device(host=cfg.ssh_host)
        self.strokes: list[list[tuple[float, float]]] = []
        # When each stroke began and ended, on the store's clock rather than
        # the tablet's: Sample.t_ms is the agent's own monotonic clock and is
        # not comparable with anything written here.
        self.stroke_times: list[tuple[int, int]] = []
        self.current: list[tuple[float, float]] = []
        self.current_began = 0
        self.last_input = 0.0
        # A nib resting on the page reports nothing, because the input core
        # drops repeated coordinates. Silence therefore only counts as a pause
        # once the pen has actually been lifted.
        self.pen_down = False
        # Which end of the pen is on the page. The nib and the eraser both come
        # through as strokes; only the tool says which one was meant.
        self.tool = "pen"
        self.turn = 0
        self.last_turn_end_ms = -1
        self.last_turn_at = 0.0
        # Set while the diary is erasing and writing, so the page watcher does
        # not mistake the diary's own work for the writer clearing the page,
        # and so an intent does not arrive in the middle of a turn.
        self.answering = threading.Event()
        self._last_beat = 0.0
        self._last_pump = 0.0

    # --- the store -------------------------------------------------------

    def _open_store(self):
        """Join the session in progress, or start one; never fail over it."""
        try:
            # Peek first: two loops both driving one digitizer through two ssh
            # pipes interleave strokes, and is worse than not starting.
            running = Store.attach(self.cfg.db)
            if running is not None:
                other = running.present("loop")
                running.conn.close()
                if other is not None:
                    raise SystemExit(
                        f"another diary answered {other // 1000}s ago; "
                        "stop it first (riddle diary stop)"
                    )
            return Store.join(self.cfg.db, "loop")
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 - a broken store must not stop the diary
            print(f"no store ({exc}); answering anyway", file=sys.stderr)
            return NoStore()

    def _remembered(self, note: str) -> None:
        """Mirror a kept line onto the timeline, so the page can show it.

        The file stays the source of truth -- it outlives the store, whose
        schema keeps changing and which is safe to delete. This is a log
        entry saying the diary chose to keep something, not a second copy.
        """
        self.store.add_event("note", text=note, meta={"remember": True})

    def beat(self) -> None:
        now = time.monotonic()
        if now - self._last_beat >= BEAT_S:
            self._last_beat = now
            self.store.beat()

    # --- housekeeping ----------------------------------------------------

    def forget(self, reason: str) -> None:
        """Start a new conversation, keeping only what was written to memory."""
        self.diary.forget()
        self.store.add_event("tool", meta={"doing": "forgetting", "why": reason})
        print(f"{reason}: forgetting the conversation", file=sys.stderr)

    def run(self) -> None:
        cfg = self.cfg
        uuid = notebook.find(cfg.notebook, cfg.ssh_host)
        found = f"({uuid[:8]})" if uuid else "(not found on device)"
        kept = len(self.memory.lines())
        print(
            f"diary open, writing into whatever page is on screen. "
            f"keep {cfg.notebook!r} {found} open. write, then pause.",
            file=sys.stderr,
        )
        print(
            f"remembering {kept} thing(s) from before" if kept else "no memories yet",
            file=sys.stderr,
        )
        print(f"session {self.store.session_id}", file=sys.stderr)

        # Only the loop ever sets an intent to running, so one left in that
        # state is one a previous loop died holding.
        abandoned = self.store.abandon_intents("the diary restarted")
        if abandoned:
            print(f"gave up on {abandoned} interrupted intent(s)", file=sys.stderr)
        self.store.add_event(
            "tool",
            meta={
                "doing": "opened",
                "host": cfg.ssh_host,
                "notebook": cfg.notebook,
                "model": cfg.model,
            },
        )

        # Turning to a new page, or wiping this one, should cost the diary the
        # conversation but not its memory. xochitl only writes a page out when
        # you leave it, so this notices shortly after the fact rather than as
        # it happens.
        page = pages.Page(cfg.ssh_host)
        threading.Thread(
            target=pages.watch,
            args=(page, self.forget, self.answering.is_set),
            daemon=True,
        ).start()

        while True:
            try:
                event = self.device.events.get(timeout=0.1)
            except queue.Empty:
                event = None

            if event is None and self.device.proc.poll() is not None:
                self.store.add_event("error", text="the device agent exited")
                raise SystemExit("device agent exited")

            if isinstance(event, Sample):
                if not self.current:
                    self.current_began = self.store.now_ms()
                self.current.append((event.x, event.y))
                self.pen_down = True
                self.last_input = time.monotonic()
            elif isinstance(event, PenUp):
                self.finish_stroke()
                self.pen_down = False
                self.last_input = time.monotonic()
            elif isinstance(event, Tool):
                self.tool = event.name
            elif isinstance(event, Touch):
                # A finger on the screen is handling the tablet, not writing:
                # it never makes a question, but it does hold the answer off
                # while a page is being scrolled or a tool picked.
                self.last_input = time.monotonic()

            self.beat()
            self.pump()

            idle = time.monotonic() - self.last_input
            if not self.pen_down and idle >= self.pause_s and self.question():
                print(f"paused {idle:.1f}s", file=sys.stderr)
                self.answer("pause")

    # --- what the pen did ------------------------------------------------

    def finish_stroke(self) -> None:
        """File the stroke that just ended, unless it was not writing."""
        stroke, self.current = self.current, []
        if not stroke:
            return
        began, ended = self.current_began, self.store.now_ms()
        if self.tool == "rubber":
            self.rub_out(stroke)
            return
        if travel(stroke) < TAP_TRAVEL:
            return  # a press: a tool in the toolbar, the page woken, a blot
        if max(x for x, _ in stroke) < TOOLBAR_X:
            return  # a drag inside the toolbar strip, e.g. a thickness slider
        self.strokes.append(stroke)
        self.stroke_times.append((began, ended))

    def rub_out(self, pass_: list[tuple[float, float]]) -> None:
        """Take the pending strokes the eraser just went over off the page."""
        keep = [
            i for i, s in enumerate(self.strokes) if not crosses(s, pass_, ERASE_RADIUS)
        ]
        if len(keep) != len(self.strokes):
            print(f"erased {len(self.strokes) - len(keep)} stroke(s)", file=sys.stderr)
        self.strokes = [self.strokes[i] for i in keep]
        self.stroke_times = [self.stroke_times[i] for i in keep]

    def question(self) -> bool:
        """Whether what is on the page is enough to be worth answering.

        A pause only means something after something was written. Three seconds
        of quiet with a dot or two on the page is quiet, not a question.
        """
        if not self.strokes:
            return False
        if sum(travel(s) for s in self.strokes) < MIN_INK:
            return False
        box = render.bounding_box(self.strokes)
        if not box:
            return False
        return max(box[2] - box[0], box[3] - box[1]) >= MIN_SPAN

    # --- what the other half asked for -----------------------------------

    def pump(self) -> None:
        """Serve anything the page asked for, between pen events.

        Three gates, all cheap. Not while the nib is down, because a Send
        pressed mid-sentence should wait for the lift anyway and the pen path
        must never wait on sqlite. Not while answering, because an intent that
        arrives mid-turn can simply stay pending and be served when the turn
        ends. And not more than a few times a second.

        The no-transaction-across-io rule holds here by construction, as long
        as nothing wraps this sequence in _tx(): the claim is one statement,
        the work happens with no transaction open, and the finish is another.
        """
        now = time.monotonic()
        if self.pen_down or self.answering.is_set() or now - self._last_pump < PUMP_S:
            return
        self._last_pump = now
        if not self.store.intent_waiting():
            return

        stale = self.store.expire_intents(
            self.store.now_ms() - INTENT_TTL_MS, "nobody was listening"
        )
        if stale:
            print(f"dropped {len(stale)} stale intent(s)", file=sys.stderr)

        claimed = []
        while True:
            intent = self.store.claim_intent()
            if intent is None:
                break
            claimed.append(intent)
        if not claimed:
            return

        # Double-tapping Send on a phone is inevitable. One turn is served and
        # the rest are told they were folded into it.
        sends = [i for i in claimed if i["action"] == "send"]
        for extra in sends[1:]:
            self.store.finish_intent(extra["id"], ok=True, result={"merged_into": sends[0]["id"]})
        for intent in claimed:
            if intent["action"] == "send" and intent is not sends[0]:
                continue
            self.serve(intent)

    def serve(self, intent: dict) -> None:
        action = intent["action"]
        if action == "send":
            self.answer("send", intent=intent)
            return
        if action == "forget":
            self.forget("asked from the page")
            self.store.finish_intent(intent["id"], ok=True, result={"forgot": True})
            return
        # Recognised and refused, rather than unknown: the page, and any other
        # thing that leaves intents, deserves a definite answer. Injecting
        # arbitrary ink into whatever notebook happens to be open is exactly
        # what the warning in the README is about, and nothing asks for it.
        reason = {
            "draw": "the diary does not take dictation of ink yet",
            "erase": "erasing from the page is not wired up yet",
            "shot": "reading the screen is not wired up yet",
        }.get(action, f"unknown action {action!r}")
        self.store.finish_intent(intent["id"], ok=False, result={"error": reason})
        self.store.add_event("error", text=reason, meta={"intent": intent["id"]})
        print(f"refused intent {intent['id']}: {reason}", file=sys.stderr)

    # --- answering -------------------------------------------------------

    def answer(self, trigger: str, intent: dict | None = None) -> None:
        self.answering.set()
        try:
            self._answer(trigger, intent)
        finally:
            self.answering.clear()

    def _answer(self, trigger: str, intent: dict | None = None) -> None:
        written, self.strokes = self.strokes, []
        times, self.stroke_times = self.stroke_times, []
        box = render.bounding_box(written) if written else None

        draft = (intent or {}).get("args", {}).get("draft") or ""
        if draft:
            # Written as a note before the window closes, so the ordinary
            # claim picks it up and it lands on the timeline where it was
            # typed rather than needing a second code path.
            self.store.add_event("note", text=draft, meta={"from": "send"})

        self.turn += 1
        turn = self.turn
        image = None
        if written:
            # Each turn gets its own file. The conversation is resumed across
            # turns, so a reused filename lets the model answer from the copy
            # of the page it already has in context instead of the one just
            # written.
            image = render.strokes_to_png(
                written, paths.CAPTURES / f"page-{int(time.time())}-{turn}.png"
            )
            self.store.add_strokes(
                written,
                times,
                turn=turn,
                path=paths.relative(image),
                meta={"during_answer": False},
            )
        print(f"[{len(written)} strokes] thinking...", file=sys.stderr)

        # The ink has to start fading the moment you stop writing, so the model
        # runs while the page is being erased rather than after it. That also
        # pays for the wait below: a sentence still inside the speech model
        # lands while the eraser is working, and costs nothing.
        pending: list = []
        erasing = None
        if written:
            erasing = threading.Thread(target=self._erase, args=(written,), daemon=True)
            erasing.start()

        self.wait_for_speech()
        to_ms = self.store.now_ms()
        from_ms = max(-1, self.last_turn_end_ms - (SEND_LOOKBACK_MS if trigger == "send" else ORPHAN_MS))
        self.store.begin_turn(turn, trigger, from_ms, to_ms)
        self.store.claim(turn, from_ms, to_ms)
        heard, typed = self.said(turn)

        if image is None and not heard and not typed:
            # A send that arrived while the diary was mid-turn finds its input
            # already claimed by the turn that just finished. Say so, rather
            # than running an empty turn and inventing a question.
            recent_turn = time.monotonic() - self.last_turn_at < 10
            reason = (
                "that was already answered"
                if trigger == "send" and recent_turn
                else "there was nothing to answer"
            )
            self.store.end_turn(turn, error=reason)
            self.store.add_event("error", text=reason, meta={"intent": (intent or {}).get("id")})
            if intent:
                self.store.finish_intent(intent["id"], ok=False, result={"error": reason})
            print(reason, file=sys.stderr)
            if erasing:
                erasing.join()
            self.settle(to_ms)
            return

        question = Question(trigger=trigger, image=image, heard=heard, typed=typed)
        self.store.add_event("tool", turn=turn, meta={"doing": "thinking"})
        thinking = threading.Thread(
            target=lambda: pending.append(self._ask(question)), daemon=True
        )
        thinking.start()
        if erasing:
            erasing.join()
        thinking.join()

        answer = pending[0] if pending else None
        if answer is None:
            self.store.end_turn(turn, error="the model returned nothing")
            if intent:
                self.store.finish_intent(intent["id"], ok=False, result={"error": "no reply"})
            if written:
                # Nothing came back, so give the writer their words again
                # rather than leaving a blank page where the question was.
                self.device.draw(written, pressure=self.pressure, step_ms=2)
                self.device.sync()
            self.settle(to_ms)
            return

        # Written before the pen moves, so the phone shows the answer while
        # the tablet is still inking it.
        self.store.add_event(
            "reply", turn=turn, text=answer.text, meta={"intent": (intent or {}).get("id")}
        )
        print(f"diary: {answer.text}", file=sys.stderr)
        time.sleep(0.4)

        self.store.add_event("tool", turn=turn, meta={"doing": "writing"})
        self.write(answer.text, box)
        self.store.end_turn(
            turn,
            reply=answer.text,
            claude_session=answer.session_id,
            cost_usd=answer.cost_usd,
        )
        if intent:
            self.store.finish_intent(intent["id"], ok=True, result={"turn": turn})
        self.settle(to_ms)

    def _erase(self, written) -> None:
        self.device.draw(written, eraser=True, step_ms=2)
        self.device.sync()

    def wait_for_speech(self) -> None:
        """Give the speech model a moment to finish the last sentence.

        Transcription lags by seconds, and a sentence spoken just before the
        pause will land on the timeline *before* the pause once it arrives. So
        the window is not closed until nothing new has been transcribed for a
        moment and no clip is still with the model. This costs nothing: it
        runs while the page is being erased.
        """
        if self.store.present("voice") is None:
            return
        deadline = time.monotonic() + min(SPEECH_GRACE_MS, SPEECH_GRACE_CAP_MS) / 1000
        quiet_since = time.monotonic()
        last_seen = self._newest_speech_id()
        while time.monotonic() < deadline:
            inflight = self.store.get_state("asr.inflight", 0) or 0
            newest = self._newest_speech_id()
            if newest != last_seen:
                last_seen, quiet_since = newest, time.monotonic()
            elif not inflight and time.monotonic() - quiet_since >= SPEECH_QUIET_MS / 1000:
                return
            time.sleep(0.1)

    def _newest_speech_id(self) -> int:
        rows = self.store.recent(kinds=["speech"], limit=1) or []
        return rows[-1]["id"] if rows else 0

    def said(self, turn: int) -> tuple[list, list]:
        """What was spoken and typed inside this turn's window."""
        claimed = self.store.recent(turn=turn, kinds=["speech", "note"], limit=40) or []
        heard = [(e["t_ms"], e["text"]) for e in claimed if e["kind"] == "speech" and e["text"]]
        typed = [(e["t_ms"], e["text"]) for e in claimed if e["kind"] == "note" and e["text"]]
        return heard, typed

    def write(self, reply: str, box) -> None:
        """Answer in the space the writing occupied, centred on the page."""
        max_width = SCREEN_W - 2 * PAGE_MARGIN
        runs = self.palette.runs(reply, self.ink_height)
        rows = hershey.line_count(runs, max_width)
        tallest = max(run.height for run in runs)
        block = (rows - 1) * tallest * 1.9

        middle = (box[1] + box[3]) / 2 if box else SCREEN_H / 2
        baseline = middle - block / 2
        baseline = max(PAGE_MARGIN + tallest, baseline)
        baseline = min(SCREEN_H - PAGE_MARGIN - block, baseline)

        ink = hershey.layout_runs(
            runs,
            center_x=SCREEN_W / 2,
            baseline=baseline,
            max_width=max_width,
        )
        # An injected stroke becomes whatever tool xochitl has active, so a
        # page of handwriting turns into a page of lasso selections if the
        # toolbar was left on the selection tool. Press the pen first.
        self.device.select("pen")
        self.device.draw(ink, pressure=self.pressure, step_ms=6)
        self.device.sync()

    def _ask(self, question: Question):
        try:
            return self.diary.reply_to(question, ago=self._ago)
        except Exception as exc:
            print(f"diary failed: {exc}", file=sys.stderr)
            self.store.add_event("error", text=f"the model failed: {exc}")
            return None

    def _ago(self, t_ms: int) -> str:
        from riddle.store.db import ago

        return ago(t_ms, self.store.now_ms())

    def settle(self, to_ms: int) -> None:
        """Restart the pause clock after the diary finishes its turn.

        Anything written by hand while the diary was drawing is still sitting
        in the queue: the agent cancels only its own echo, so those strokes
        survive and become the next question.
        """
        # The diary just drove the tool back and forth to erase and write. If
        # one of those switches escaped echo cancellation the host would think
        # the writer is holding the eraser; assume the nib until the pen says
        # otherwise, which it does the moment it comes near the page.
        self.tool = "pen"
        self.last_input = time.monotonic()
        self.last_turn_end_ms = to_ms
        self.last_turn_at = time.monotonic()


def main() -> None:
    config.get()
    paths.ensure()
    session = Session()
    try:
        session.run()
    except KeyboardInterrupt:
        pass
    finally:
        session.device.close()
        session.store.close()


if __name__ == "__main__":
    main()
