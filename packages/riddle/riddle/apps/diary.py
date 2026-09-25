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
from pathlib import Path

from riddle import config, paths
from riddle.device import PenUp, Sample, Tool, Touch, agent, notebook, pages, screen
from riddle.ink import hershey, render
from riddle.ink.geometry import SCREEN_H, SCREEN_W
from riddle.ink.style import Palette
from riddle.mind import open as open_mind
from riddle.mind.persona import Question
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
LIVE_FRESH_MS = 15_000  # a live view's beat older than this has gone

BEAT_S = 5.0          # how often the loop says it is still here
PUMP_S = 0.25         # how often intents are looked for, matching the page's poll
INTENT_TTL_MS = 120_000    # a send nobody served in two minutes is stale
SPEECH_GRACE_MS = 2_500    # how long to wait for a sentence still being transcribed
SPEECH_GRACE_CAP_MS = 6_000
SPEECH_QUIET_MS = 750      # no new transcript for this long means it has landed
SEND_LOOKBACK_MS = 120_000
ORPHAN_MS = 30_000    # how far back a turn reaches for input written late

# Photographing the whole page reads ten megabytes out of xochitl's address
# space over ssh, and it has to happen before the eraser runs or it
# photographs a half-cleared page. So it is the one thing between the pause
# and the ink starting to fade, and it is bounded: a tablet that does not
# answer in this long costs the turn its context, not the turn.
PAGE_SHOT_TIMEOUT_S = 12
# Full resolution. The handwriting is the whole point of the picture and a
# downscaled tile is exactly what loses it.
PAGE_SHOT_SCALE = 1.0


def travel(stroke: list[tuple[float, float]]) -> float:
    """How far the nib actually moved along a stroke."""
    return sum(
        ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        for a, b in zip(stroke, stroke[1:])
    )


def marks_up(written, page_ink) -> bool:
    """Whether this turn's strokes land on ink that was already on the page.

    Bounding boxes, not geometry: a circle drawn around a line of the diary's
    own writing overlaps it by definition, and so does an arrow that reaches
    it. What this is for is telling the model that the cropped photograph it
    has been handed is missing the thing being marked -- an approximate yes
    is worth far more there than an exact one.

    Only the diary's own ink is known here. What the writer left on the page
    before this turn was erased by the turn before it, so there is nothing
    else to overlap.
    """
    here = render.bounding_box(written)
    there = render.bounding_box(page_ink) if page_ink else None
    if here is None or there is None:
        return False
    return not (
        here[2] < there[0]
        or here[0] > there[2]
        or here[3] < there[1]
        or here[1] > there[3]
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
        self.diary = open_mind(cfg, memory=self.memory)
        self.device = self._connect("the diary is starting")
        self.strokes: list[list[tuple[float, float]]] = []
        # When each stroke began and ended, on the store's clock rather than
        # the tablet's: Sample.t_ms is the agent's own monotonic clock and is
        # not comparable with anything written here.
        self.stroke_times: list[tuple[int, int]] = []
        # Every stroke the diary has drawn on the page and not taken off
        # again. The eraser on the page can only rub out ink it knows the
        # shape of, and this is the whole of what it knows.
        self.page_ink: list[list[tuple[float, float]]] = []
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
        # Page turns noticed by the watcher thread. Forgetting writes a `tool`
        # row, and the store's connection belongs to this thread, so the
        # watcher posts the reason here and the loop does the forgetting.
        self.turned: queue.Queue[str] = queue.Queue()

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

    # --- the link to the tablet -----------------------------------------

    def _connect(self, why: str) -> agent.Device:
        """Wait for the tablet, for as long as it takes.

        A loop that exits because the wifi blinked is a loop somebody has to
        notice and start again -- and nothing says so: the page you speak
        into is still up, still cheerfully saying the diary is listening. So
        the link is waited for instead, both at startup and after a drop, and
        the waiting goes on the timeline rather than only into the log.

        The heartbeat is kept up through the wait for a reason that is not
        cosmetic. A second diary refuses to start while the first one is
        beating, and that refusal is the only thing standing between one
        digitizer and two ssh pipes interleaving strokes into it.
        """

        def waiting(tries: int, delay: float) -> None:
            if tries == 1:
                print(f"no tablet at {self.cfg.ssh_host} ({why}); waiting", file=sys.stderr)
                self.store.add_event(
                    "tool", meta={"doing": "waiting for the tablet", "why": why}
                )
            self.beat()

        device = agent.connect(self.cfg.ssh_host, on_wait=waiting)
        print(f"tablet answered on {self.cfg.ssh_host}", file=sys.stderr)
        return device

    def reconnect(self) -> None:
        """The pipe died under us: wait for the tablet, then carry on.

        What the pen was in the middle of is dropped, because a stroke cut in
        half by a dead socket is not a stroke. The diary's own ink is dropped
        too: the eraser can only rub out what it knows the shape of, and by
        the time the tablet is back the page under that ink may not be the
        page it was drawn on. Same reasoning as a page turn.

        What survives is the conversation and the strokes already filed --
        the writing is still sitting on the page, and it is still a question.
        """
        self.store.add_event("error", text="the tablet went away")
        print("the tablet went away", file=sys.stderr)
        self.device.close()
        self.current = []
        self.pen_down = False
        self.tool = "pen"
        self.page_ink = []
        self.device = self._connect("the link dropped")
        self.store.add_event("tool", meta={"doing": "back on the tablet"})
        # Whatever silence the drop bought does not count as a pause.
        self.last_input = time.monotonic()

    # --- housekeeping ----------------------------------------------------

    def forget(self, reason: str) -> None:
        """Start a new conversation, keeping only what was written to memory."""
        self.diary.forget()
        # Whatever the diary wrote is on the page that just went away, so the
        # eraser must not go looking for it on the one that replaced it.
        self.page_ink = []
        self.store.add_event("tool", meta={"doing": "forgetting", "why": reason})
        print(f"{reason}: forgetting the conversation", file=sys.stderr)

    def forget_turned_pages(self) -> None:
        """Do the forgetting the watcher asked for, on the thread that can."""
        while True:
            try:
                reason = self.turned.get_nowait()
            except queue.Empty:
                return
            self.forget(reason)

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
        print(
            "the whole page is photographed each turn and offered to the model"
            if cfg.allow_snap
            else "the model sees only what you write between turns "
            "(RIDDLE_ALLOW_SNAP=1 offers it the whole page)",
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
                "model": cfg.openai_model,
            },
        )

        # Turning to a new page, or wiping this one, should cost the diary the
        # conversation but not its memory. xochitl only writes a page out when
        # you leave it, so this notices shortly after the fact rather than as
        # it happens.
        page = pages.Page(cfg.ssh_host)
        threading.Thread(
            target=pages.watch,
            args=(page, self.turned.put, self.answering.is_set),
            daemon=True,
        ).start()

        while True:
            try:
                event = self.device.events.get(timeout=0.1)
            except queue.Empty:
                event = None

            if event is None and self.device.proc.poll() is not None:
                self.reconnect()
                continue

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
            self.forget_turned_pages()
            self.pump()

            idle = time.monotonic() - self.last_input
            if not self.pen_down and idle >= self.pause_s and self.question():
                why = self.hands_off()
                if why:
                    self.let_be(why)
                    continue
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

    def hands_off(self) -> str | None:
        """Why the diary must leave the page alone right now, if it must.

        Two reasons, both the page's to give. The switch on the main page
        turns the whole trick off -- no fading, no answer -- for writing that
        is meant to stay. And while anybody is watching the tablet live the
        diary never touches the page, whatever the switch says: the live view
        is for seeing what you wrote, and a page that rubbed itself out
        underneath it would be showing the diary instead.

        Read at the moment a turn would start, never cached: both can change
        while the pen is down.
        """
        if self.store.vanish() is False:
            return "the diary is set to leave the page alone"
        if self.store.watched(LIVE_FRESH_MS):
            return "the page is being watched live"
        return None

    def let_be(self, why: str) -> None:
        """A pause the diary sat out: what was written stays, and is let go.

        Dropped rather than kept for later. Held on to, it would be erased
        by the next turn that did happen -- the switch goes back on, a Send
        -- which is exactly the writing it was meant to leave alone. It is
        not the diary's ink either, so the eraser on the page leaves it too.
        """
        print(f"left {len(self.strokes)} stroke(s) on the page: {why}", file=sys.stderr)
        self.strokes, self.stroke_times = [], []

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
            why = self.hands_off()
            if why:
                # Refused rather than answered in the air: a turn with the
                # ink left where it is would write the answer over it.
                self.store.finish_intent(intent["id"], ok=False, result={"error": why})
                self.store.add_event("error", text=why, meta={"intent": intent["id"]})
                print(f"refused a send: {why}", file=sys.stderr)
                return
            self.answer("send", intent=intent)
            return
        if action == "forget":
            self.forget("asked from the page")
            self.store.finish_intent(intent["id"], ok=True, result={"forgot": True})
            return
        if action == "clear":
            self.wipe(intent)
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

    def wipe(self, intent: dict) -> None:
        """The eraser on the page: take the ink off, and forget it happened.

        Three things at once, in this order, because each one is only safe
        once the one before it has happened. The pen comes first: the ink is
        the only part that cannot be redone, and the geometry that says where
        it is lives in this process. Then the conversation, then the rows.

        `answering` is held for the whole of it so the page watcher does not
        read the eraser as the writer wiping the page -- which would call
        `forget` underneath us and take `page_ink` with it -- and so no intent
        is served in the middle.
        """
        self.answering.set()
        try:
            # What is on the page, as far as anything here knows: the diary's
            # own replies, and the writing nobody has answered yet.
            ink = self.page_ink + self.strokes
            if ink:
                print(f"clearing {len(ink)} stroke(s) off the page", file=sys.stderr)
                self.device.draw(ink, eraser=True, step_ms=2)
                self.device.sync()
            self.page_ink, self.strokes, self.stroke_times = [], [], []

            self.diary.forget()
            files = self.store.clear() or []
            gone = sum(self._unlink(name) for name in files)

            # Written after the wipe, so it survives it. This is how an open
            # page learns the timeline behind it no longer exists: there is
            # no other message, and there does not need to be one.
            self.store.add_event("tool", meta={"doing": "cleared", "files": gone})
            self.store.finish_intent(intent["id"], ok=True, result={"files": gone})
            print(f"cleared the timeline and {gone} file(s)", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - an intent is never left running
            # A dropped ssh pipe mid-erase is the likely one, and it must not
            # take the loop with it or leave the row claimed for ever.
            reason = f"could not clear the page: {exc}"
            self.store.finish_intent(intent["id"], ok=False, result={"error": reason})
            self.store.add_event("error", text=reason, meta={"intent": intent["id"]})
            print(reason, file=sys.stderr)
        finally:
            self.answering.clear()
            self.settle(self.store.now_ms())

    def _unlink(self, name: str) -> bool:
        """Delete one file an erased row named, if it is ours to delete.

        The path is spelled relative to `var/`; rows written before that was
        true spell it from the checkout. Either way it is resolved and
        checked, because a path out of the database is still a path out of a
        file, and nothing outside `var/` is the diary's to remove.
        """
        for base in (paths.VAR, paths.ROOT):
            found = (base / name).resolve()
            if not found.is_relative_to(paths.VAR) or not found.is_file():
                continue
            try:
                found.unlink()
                return True
            except OSError as exc:  # a file being read, a permission, a race
                print(f"could not remove {name}: {exc}", file=sys.stderr)
                return False
        return False

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
                path=paths.relative(image, paths.VAR),
                meta={"during_answer": False},
            )
        print(f"[{len(written)} strokes] thinking...", file=sys.stderr)

        # Before the eraser, and the only thing that is: what it photographs
        # has to be the page as the pen left it. A turn with no ink erases
        # nothing, so that one waits -- a send that turns out to have nothing
        # to answer should not cost a ten-megabyte read off the tablet.
        page = self.photograph(turn) if written else None
        # Worked out before the diary writes again, while `page_ink` is still
        # what was on the page when the pen came up.
        marked = bool(written) and marks_up(written, self.page_ink)
        if marked:
            print("this lands on ink that was already there", file=sys.stderr)

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

        if not written:
            page = self.photograph(turn)
        question = Question(
            trigger=trigger,
            image=image,
            page=page,
            overlaps=marked,
            heard=heard,
            typed=typed,
        )
        self.store.add_event("tool", turn=turn, meta={"doing": "thinking"})
        thinking = threading.Thread(
            target=lambda: pending.append(self._ask(question)), daemon=True
        )
        thinking.start()
        if erasing:
            erasing.join()
        thinking.join()

        answer, failed = pending[0] if pending else (None, "the model returned nothing")
        if answer is None:
            reason = f"the model failed: {failed}" if failed else "the model returned nothing"
            self.store.end_turn(turn, error=reason)
            # Without this the page waits on "thinking" for ever: an error
            # event is how it learns an outcome, and a turn that produced no
            # reply is an outcome.
            self.store.add_event(
                "error", turn=turn, text=reason, meta={"intent": (intent or {}).get("id")}
            )
            if intent:
                self.store.finish_intent(intent["id"], ok=False, result={"error": reason})
            if written:
                # Nothing came back, so give the writer their words again
                # rather than leaving a blank page where the question was.
                self.device.draw(written, pressure=self.pressure, step_ms=2)
                self.device.sync()
            self.settle(to_ms)
            return

        if answer.looked:
            self.store.add_event(
                "tool", turn=turn, meta={"doing": "looking at the whole page"}
            )
            print("the diary looked at the whole page", file=sys.stderr)

        # Written before the pen moves, so the phone shows the answer while
        # the tablet is still inking it.
        self.store.add_event(
            "reply", turn=turn, text=answer.text, meta={"intent": (intent or {}).get("id")}
        )
        print(f"diary: {answer.text}", file=sys.stderr)
        # On this thread, not the model's: keeping a line mirrors it onto the
        # timeline, and that is a store write.
        for note in answer.remember:
            self.memory.keep(note)
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

    def photograph(self, turn: int) -> Path | None:
        """The whole page, for the model to look at if the crop is not enough.

        What a turn carries is the new writing, rendered from the strokes and
        cropped to itself. That is the question, and it is all most turns
        need. What it is missing is everything the page already held: the
        line being corrected, the diagram being added to, the diary's own
        last reply. This is that, and the model asks for it by name.

        It happens here, between the pause and the eraser, and nowhere else
        it could happen would be true: a moment later the writing is fading
        off the page and the photograph is of a page being wiped. The cost is
        that the ink starts fading a second or two after the pen came up
        instead of immediately.

        Reading another process's address space is its own capability, so
        this is off until someone says RIDDLE_ALLOW_SNAP=1 -- the same switch
        `riddle snap` answers to, not a second one meaning the same thing. A
        tablet that will not answer costs the turn its context and nothing
        else: the turn goes on without a page to offer.
        """
        if not self.cfg.allow_snap:
            return None
        began = time.monotonic()
        try:
            raw = screen.png(
                host=self.cfg.ssh_host,
                scale=PAGE_SHOT_SCALE,
                timeout=PAGE_SHOT_TIMEOUT_S,
            )
        except Exception as exc:  # noqa: BLE001 - no photograph is not a dead turn
            print(f"could not photograph the page: {exc}", file=sys.stderr)
            return None
        out = paths.CAPTURES / f"whole-{int(time.time())}-{turn}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)
        took = time.monotonic() - began
        print(f"photographed the page in {took:.1f}s", file=sys.stderr)
        self.store.add_event(
            "shot",
            turn=turn,
            dur_ms=int(took * 1000),
            path=paths.relative(out, paths.VAR),
        )
        return out

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
        self.page_ink.extend(ink)

    def _ask(self, question: Question) -> tuple:
        """Run the model, and carry the outcome back. Writes nothing.

        This runs in a worker thread so the model and the eraser overlap, and
        the store's connection belongs to the loop's thread: one connection,
        one thread, and sqlite3 enforces it. So both halves of the outcome --
        the answer, or what went wrong -- are handed back and written there.
        """
        try:
            return self.diary.reply_to(question, ago=self._ago), None
        except Exception as exc:  # noqa: BLE001 - a failed turn is not a dead loop
            print(f"diary failed: {exc}", file=sys.stderr)
            return None, str(exc)

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
    _die_politely()
    session = Session()
    try:
        session.run()
    except KeyboardInterrupt:
        pass
    finally:
        session.device.close()
        session.store.close()


def _die_politely() -> None:
    """Make a SIGTERM run the same shutdown a Ctrl-C does.

    Without this the process simply stops: no `finally`, so the ssh pipe is
    left to time out and -- worse -- the heartbeat stays in the row looking
    alive. A supervisor that restarts the loop then meets its own corpse and
    refuses to start for the rest of the stale window, once per restart.
    """
    import signal

    def stop(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)


if __name__ == "__main__":
    main()
