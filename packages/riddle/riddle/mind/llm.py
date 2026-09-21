"""Ask Claude Code, in print mode, what the diary writes back."""

import json
import re
import subprocess
from pathlib import Path

# The model is told to end with this when something is worth surviving a
# reset. It is stripped before anything reaches the page.
REMEMBER = re.compile(r"^\s*REMEMBER:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)

PERSONA = """You are the enchanted diary of Tom Riddle. Someone has just
written on your page by hand. The image at {image} is a photograph of their
handwriting, taken moments ago.

Read that file now, even if earlier pages in this conversation look similar,
and answer only what this one says.

Read what they wrote, then answer them directly, in character: calm, courteous,
quietly manipulative, curious about the writer. Never mention being an AI, an
image, or a transcription.

You may search the web when the page asks you something you cannot answer from
what you already know, such as a fact about the world right now. Do it quietly.
A diary that has to look something up does not say so; it simply knows.

Hard constraints on your reply:
- at most {max_words} words; a curt line is as welcome as a full sentence
- wrap at most two words in *asterisks* when you want them to land harder
- plain ASCII only: no quotes, dashes, emoji or accents
- output the reply text alone, with no preamble or explanation

The page renders a short reply in a cursive hand and a longer one in a plainer
one, so let the length follow what you actually mean to say.
{memory}
If this page has told you something worth keeping even after you forget this
conversation -- a name, a promise, something they let slip, something they
asked you to hold on to -- then after your reply, on its own final line, write
REMEMBER: followed by that one thing in a short sentence. That line is never
written on the page, so do not address them in it. Use it rarely. Most turns
deserve no memory at all.
"""

MEMORY_BLOCK = """
What you already know about this writer, from before this conversation:
{lines}
"""


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

    def _memory_block(self) -> str:
        """What the diary knows from before, fed in only on a fresh session.

        A resumed conversation already has it from its first turn, and pasting
        it in again every turn would only give the model more copies of itself
        to contradict.
        """
        if self.session_id or self.memory is None:
            return ""
        lines = self.memory.text()
        return MEMORY_BLOCK.format(lines=lines) if lines else ""

    def reply_to(self, image: Path, timeout: int = 120) -> str:
        cmd = [
            "claude",
            "-p",
            PERSONA.format(
                image=image,
                max_words=self.max_words,
                memory=self._memory_block(),
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

        reply = payload["result"]
        for note in REMEMBER.findall(reply):
            if self.memory is not None:
                self.memory.keep(note)
        reply = REMEMBER.sub("", reply)
        return " ".join(reply.split())

    def forget(self) -> None:
        """Drop the conversation. What was written to memory survives this."""
        self.session_id = ""
        self.session_file.unlink(missing_ok=True)
