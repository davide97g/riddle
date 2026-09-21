#!/usr/bin/env python3
"""Tom Riddle diary for the reMarkable 2.

Write on a page. Pause. What you wrote fades off the page and the diary
answers you in ink, in its own hand.
"""

import os
import queue
import sys
import threading
import time
from pathlib import Path

import hershey
import notebook
import render
from geometry import SCREEN_H, SCREEN_W
import recall
from device import Device, PenUp, Sample, Tool, Touch
from llm import Diary
from style import Palette

ROOT = Path(__file__).resolve().parent.parent
PAGE_MARGIN = 70

# What counts as writing, and what is only handling the tablet. Every one of
# these arrives as pen input and none of them is a question: pressing a tool in
# the toolbar, poking the page awake, rubbing something out, leaving a blot.
TOOLBAR_X = 110       # screen px: a stroke wholly inside the left strip is UI
TAP_TRAVEL = 25       # px of travel below which a stroke is a press, not a mark
MIN_INK = 500         # px of travel before the page holds anything to answer
MIN_SPAN = 110        # px of bounding box: a word is wider than a dot
ERASE_RADIUS = 28     # px: an eraser pass this close takes the stroke with it


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


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


class Session:
    def __init__(self) -> None:
        self.pause_s = float(env("RIDDLE_PAUSE_MS", "3000")) / 1000
        self.ink_height = float(env("RIDDLE_INK_HEIGHT", "72"))
        self.pressure = int(env("RIDDLE_PRESSURE", "3200"))
        self.palette = Palette(
            body=env("RIDDLE_FONT_BODY", "futural"),
            accent=env("RIDDLE_FONT_ACCENT", "scripts"),
        )
        self.memory = recall.Memory(ROOT / "memories.txt")
        self.diary = Diary(
            model=env("RIDDLE_MODEL", "claude-sonnet-5"),
            max_words=int(env("RIDDLE_MAX_WORDS", "22")),
            session_file=ROOT / ".riddle_session",
            memory=self.memory,
        )
        self.device = Device(host=env("RM2_SSH_HOST", "rm2"))
        self.strokes: list[list[tuple[float, float]]] = []
        self.current: list[tuple[float, float]] = []
        self.last_input = 0.0
        # A nib resting on the page reports nothing, because the input core
        # drops repeated coordinates. Silence therefore only counts as a pause
        # once the pen has actually been lifted.
        self.pen_down = False
        # Which end of the pen is on the page. The nib and the eraser both come
        # through as strokes; only the tool says which one was meant.
        self.tool = "pen"
        self.turn = 0
        # Set while the diary is erasing and writing, so the page watcher does
        # not mistake the diary's own work for the writer clearing the page.
        self.answering = threading.Event()

    def forget(self, reason: str) -> None:
        """Start a new conversation, keeping only what was written to memory."""
        self.diary.forget()
        print(f"{reason}: forgetting the conversation", file=sys.stderr)

    def run(self) -> None:
        host = env("RM2_SSH_HOST", "rm2")
        target = env("RIDDLE_NOTEBOOK", "Notebook")
        uuid = notebook.find(target, host)
        found = f"({uuid[:8]})" if uuid else "(not found on device)"
        kept = len(self.memory.lines())
        print(
            f"diary open, writing into whatever page is on screen. "
            f"keep {target!r} {found} open. write, then pause.",
            file=sys.stderr,
        )
        print(
            f"remembering {kept} thing(s) from before"
            if kept
            else "no memories yet",
            file=sys.stderr,
        )

        # Turning to a new page, or wiping this one, should cost the diary the
        # conversation but not its memory. xochitl only writes a page out when
        # you leave it, so this notices shortly after the fact rather than as
        # it happens.
        page = recall.Page(host)
        threading.Thread(
            target=recall.watch,
            args=(page, self.forget, self.answering.is_set),
            daemon=True,
        ).start()
        while True:
            try:
                event = self.device.events.get(timeout=0.1)
            except queue.Empty:
                event = None

            if event is None and self.device.proc.poll() is not None:
                raise SystemExit("device agent exited")

            if isinstance(event, Sample):
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

            idle = time.monotonic() - self.last_input
            if not self.pen_down and idle >= self.pause_s and self.question():
                print(f"paused {idle:.1f}s", file=sys.stderr)
                self.answer()

    def finish_stroke(self) -> None:
        """File the stroke that just ended, unless it was not writing."""
        stroke, self.current = self.current, []
        if not stroke:
            return
        if self.tool == "rubber":
            self.rub_out(stroke)
            return
        if travel(stroke) < TAP_TRAVEL:
            return  # a press: a tool in the toolbar, the page woken, a blot
        if max(x for x, _ in stroke) < TOOLBAR_X:
            return  # a drag inside the toolbar strip, e.g. a thickness slider
        self.strokes.append(stroke)

    def rub_out(self, pass_: list[tuple[float, float]]) -> None:
        """Take the pending strokes the eraser just went over off the page."""
        kept = [s for s in self.strokes if not crosses(s, pass_, ERASE_RADIUS)]
        if len(kept) != len(self.strokes):
            print(
                f"erased {len(self.strokes) - len(kept)} stroke(s)", file=sys.stderr
            )
        self.strokes = kept

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

    def answer(self) -> None:
        self.answering.set()
        try:
            self._answer()
        finally:
            self.answering.clear()

    def _answer(self) -> None:
        written, self.strokes = self.strokes, []
        box = render.bounding_box(written)
        # Each turn gets its own file. The conversation is resumed across
        # turns, so a reused filename lets the model answer from the copy of
        # the page it already has in context instead of the one just written.
        self.turn += 1
        image = render.strokes_to_png(
            written, ROOT / "captures" / f"page-{int(time.time())}-{self.turn}.png"
        )
        print(f"[{len(written)} strokes] thinking...", file=sys.stderr)

        # The ink has to start fading the moment you stop writing, so the model
        # runs while the page is being erased rather than after it.
        pending: list = []
        thinking = threading.Thread(
            target=lambda: pending.append(self._ask(image)), daemon=True
        )
        thinking.start()

        self.device.draw(written, eraser=True, step_ms=2)
        self.device.sync()
        thinking.join()

        reply = pending[0] if pending else None
        if reply is None:
            # Nothing came back, so give the writer their words again rather
            # than leaving a blank page where the question used to be.
            self.device.draw(written, pressure=self.pressure, step_ms=2)
            self.device.sync()
            self.settle()
            return

        print(f"diary: {reply}", file=sys.stderr)
        time.sleep(0.4)

        self.write(reply, box)
        self.settle()

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

    def _ask(self, image: Path) -> str | None:
        try:
            return self.diary.reply_to(image)
        except Exception as exc:
            print(f"diary failed: {exc}", file=sys.stderr)
            return None

    def settle(self) -> None:
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


def main() -> None:
    session = Session()
    try:
        session.run()
    except KeyboardInterrupt:
        pass
    finally:
        session.device.close()


if __name__ == "__main__":
    main()
