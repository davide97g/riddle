"""Host side of the link to the tablet agent.

The agent runs on the reMarkable over ssh; pen samples arrive on its stdout
and drawing commands go back down its stdin. Keeping the transport on the ssh
pipe means nothing has to listen on a port on the device.

The link works over wifi as well as the usb cable, and that is not luck: every
delay in a stroke is a SLEEP the *agent* performs, so the host only has to get
the commands there in time. Latency shifts a stroke, it does not distort it.
What wifi does change is that the link can now drop -- the tablet sleeps, the
access point roams -- so the ssh options below fail fast and loudly rather than
leaving a half-drawn stroke hanging on a dead socket.
"""

import os
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass

from riddle.device import taps as tap_store
from riddle.ink.geometry import (
    PRESSURE_MAX,
    resample,
    screen_to_wacom,
    wacom_to_screen,
)

from riddle.device.ssh import INTERACTIVE as SSH_OPTIONS, REMOTE_AGENT


@dataclass
class Sample:
    t_ms: int
    x: float
    y: float
    pressure: int


@dataclass
class Touch:
    """A finger sample, in the touchscreen's own coordinates."""

    x: int
    y: int


@dataclass
class Tool:
    """Which end of the pen is over the page: "pen" or "rubber"."""

    name: str


class PenUp:
    """Marker pushed onto the event queue when the nib leaves the page."""

    def __init__(self, t_ms: int) -> None:
        self.t_ms = t_ms


class Device:
    def __init__(self, host: str | None = None, agent: str = REMOTE_AGENT) -> None:
        # Default to the env knob rather than the cable, so every tool follows
        # the same route as the diary itself once wifi is selected.
        host = host or os.environ.get("RM2_SSH_HOST", "rm2")
        self.events: queue.Queue = queue.Queue()
        self._pongs: queue.Queue = queue.Queue()
        self.host = host
        self.proc = subprocess.Popen(
            ["ssh", *SSH_OPTIONS, host, agent],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        # Anything the agent complains about has to reach a person, and an
        # unread pipe would eventually block it mid-stroke.
        self._errors = threading.Thread(target=self._error_loop, daemon=True)
        self._errors.start()

    def _read_loop(self) -> None:
        for line in self.proc.stdout:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "P" and len(parts) == 5:
                t_ms, wx, wy, pressure = (int(v) for v in parts[1:])
                x, y = wacom_to_screen(wx, wy)
                self.events.put(Sample(t_ms, x, y, pressure))
            elif parts[0] == "U":
                self.events.put(PenUp(int(parts[1])))
            elif parts[0] == "K" and len(parts) == 2:
                self.events.put(Tool(parts[1].lower()))
            elif parts[0] == "T" and len(parts) == 3:
                self.events.put(Touch(int(parts[1]), int(parts[2])))
            elif parts[0] == "PONG":
                self._pongs.put(True)
        self.events.put(None)

    def _error_loop(self) -> None:
        assert self.proc.stderr is not None
        for line in self.proc.stderr:
            print(f"riddled: {line.rstrip()}", file=sys.stderr)

    def _send(self, line: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()

    def draw(
        self,
        strokes: list[list[tuple[float, float]]],
        pressure: int = 2400,
        step_ms: int = 6,
        eraser: bool = False,
        spacing: float = 3.0,
        settle_ms: int = 25,
    ) -> None:
        """Replay strokes onto the page as pen or eraser input.

        The step and settle defaults were read off a ladder on firmware 3.28:
        anything faster and xochitl drops samples, which shows up as letters
        broken mid-stroke rather than as anything you would call lag.
        """
        self._send("TOOL RUBBER" if eraser else "TOOL PEN")
        for stroke in strokes:
            points = resample(stroke, spacing)
            if not points:
                continue
            wx, wy = screen_to_wacom(*points[0])
            self._send(f"DOWN {wx} {wy} {min(pressure, PRESSURE_MAX)}")
            for x, y in points[1:]:
                wx, wy = screen_to_wacom(x, y)
                self._send(f"MOVE {wx} {wy} {min(pressure, PRESSURE_MAX)}")
                if step_ms:
                    self._send(f"SLEEP {step_ms}")
            self._send("UP")
            self._send(f"SLEEP {settle_ms}")
        if eraser:
            self._send("TOOL PEN")

    def tap(self, x: int, y: int, hold_ms: int = 90) -> None:
        """Press the screen where a finger once pressed it."""
        self._send(f"TAP {x} {y} {hold_ms}")

    def press(self, x: float, y: float, pressure: int = 2600, hold_ms: int = 70) -> None:
        """Poke the screen with the pen: the toolbar is usually pressed, not touched."""
        wx, wy = screen_to_wacom(x, y)
        self._send("TOOL PEN")
        self._send(f"DOWN {wx} {wy} {pressure}")
        self._send(f"SLEEP {hold_ms}")
        self._send("UP")

    def replay(self, taps: list[dict], gap_ms: int = 500) -> None:
        """Repeat a recorded sequence of toolbar presses."""
        for tap in taps:
            if tap.get("kind") == "touch":
                self.tap(int(tap["x"]), int(tap["y"]))
            else:
                self.press(float(tap["x"]), float(tap["y"]))
            self._send(f"SLEEP {gap_ms}")

    def select(self, name: str) -> bool:
        """Press the toolbar so a known tool is active before drawing.

        Injected strokes become whatever xochitl has selected, so this is the
        difference between a drawing and a page of lasso selections.
        """
        recorded = tap_store.get(name)
        if not recorded:
            print(f"no taps recorded for {name!r}", file=sys.stderr)
            return False
        self.replay(recorded)
        self._send("SLEEP 400")
        return True

    def alive(self) -> bool:
        """Whether the agent is still on the other end of the pipe."""
        return self.proc.poll() is None

    def sync(self, timeout: float = 600.0) -> None:
        """Block until the tablet has worked through everything queued.

        The agent handles stdin strictly in order, so a PING that comes back
        means every stroke before it has already been drawn.
        """
        self._send("PING")
        try:
            self._pongs.get(timeout=timeout)
        except queue.Empty:
            print("device did not answer PING", file=sys.stderr)

    def close(self) -> None:
        try:
            self._send("QUIT")
        except (BrokenPipeError, ValueError):
            pass
        self.proc.terminate()
