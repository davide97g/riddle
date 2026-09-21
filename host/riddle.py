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
from device import Device, PenUp, Sample
from llm import Diary
from style import Palette

ROOT = Path(__file__).resolve().parent.parent
PAGE_MARGIN = 70


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
                if self.current:
                    self.strokes.append(self.current)
                    self.current = []
                self.pen_down = False
                self.last_input = time.monotonic()

            idle = time.monotonic() - self.last_input
            if self.strokes and not self.pen_down and idle >= self.pause_s:
                print(f"paused {idle:.1f}s", file=sys.stderr)
                self.answer()

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
