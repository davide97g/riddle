"""Ask Claude Code, in print mode, what the diary writes back.

The whole prompt goes in on the command line and the conversation is resumed
by session id, so the model keeps the thread and this module keeps almost
nothing. It can see the page itself -- `Read` is an allowed tool and the
capture is named in the prompt -- and it can search the web, which is why this
is still the backend to pick when a turn is worth the wait.

The words it is told are in `riddle.mind.persona`, shared with the backend
that does not have any of that.
"""

import json
import subprocess
from pathlib import Path

from riddle.mind.persona import (
    CLOSING,
    PERSONA,
    SEARCH,
    Answer,
    Question,
    memory_block,
    strip_memories,
)


class Diary:
    """One conversation with the diary, resumed across turns."""

    def __init__(
        self,
        model: str,
        max_words: int,
        session_file: Path,
        memory=None,
    ) -> None:
        self.model = model
        self.max_words = max_words
        self.session_file = session_file
        self.memory = memory
        self.session_id = (
            session_file.read_text().strip() if session_file.exists() else ""
        )

    def reply_to(self, question, ago=None, timeout: int = 120) -> Answer | None:
        """Ask, and get back the reply with what it cost.

        `ago` renders a session-relative timestamp as words; the store owns
        that, and passing it keeps this module from importing the store.
        """
        if isinstance(question, Path):  # the old shape: an image and nothing else
            question = Question(image=question)
        ago = ago or (lambda t_ms: "a moment ago")
        cmd = [
            "claude",
            "-p",
            PERSONA.format(
                happened=question.happened(ago),
                # It can open the capture itself, and it has the web.
                search=SEARCH,
                max_words=self.max_words,
                # A resumed conversation already carries the memory from its
                # first turn; only a fresh session needs it pasted in.
                memory=memory_block(self.memory, first_turn=not self.session_id),
                closing=CLOSING.get(question.trigger, CLOSING["pause"]),
            ),
            "--model",
            self.model,
            "--output-format",
            "json",
            "--allowedTools",
            "Read,WebSearch,WebFetch",
        ]
        if self.session_id:
            cmd += ["--resume", self.session_id]

        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if done.returncode != 0:
            raise RuntimeError(done.stderr.strip() or "claude failed")

        payload = json.loads(done.stdout)
        if payload.get("is_error"):
            raise RuntimeError(payload.get("result", "claude reported an error"))

        self.session_id = payload.get("session_id", "")
        if self.session_id:
            self.session_file.write_text(self.session_id)

        reply, kept = strip_memories(payload["result"])
        return Answer(
            text=" ".join(reply.split()),
            session_id=self.session_id,
            cost_usd=payload.get("total_cost_usd"),
            duration_ms=payload.get("duration_ms"),
            remember=kept,
        )

    def forget(self) -> None:
        """Drop the conversation. What was written to memory survives this."""
        self.session_id = ""
        self.session_file.unlink(missing_ok=True)
