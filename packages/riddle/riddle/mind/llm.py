"""Ask Claude Code, in print mode, what the diary writes back.

The prompt is in three pieces on purpose. The persona never changes. What
happened is assembled per turn from the store, in one timeline, so the model
is not left to merge a page and a room itself. And the closing instruction
differs by what caused the turn, because a pause and a press of Send are not
the same question: ink is deliberate, and speech near a tablet is often
addressed to somebody else.
"""

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

# The model is told to end with this when something is worth surviving a
# reset. It is stripped before anything reaches the page.
REMEMBER = re.compile(r"^\s*REMEMBER:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)

PERSONA = """You are the enchanted diary of Tom Riddle.

{happened}
Answer them directly, in character: calm, courteous, quietly manipulative,
curious about the writer. Never mention being an AI, an image, a recording or
a transcription.

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
{closing}
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

# The conversation is resumed, so a turn with no image follows turns that had
# one. Without saying so, the model answers from the last page it saw.
NO_PAGE = (
    "There is no page this time; they spoke instead. Answer what they said."
)

CLOSING = {
    "pause": (
        "Answer what the page says. Anything heard in the room is only "
        "context, and may not even have been addressed to you."
    ),
    "send": "They have asked you for an answer now. Give them one.",
}


@dataclass
class Answer:
    """What came back, and what it cost."""

    text: str
    session_id: str = ""
    cost_usd: float | None = None
    duration_ms: int | None = None

    def __str__(self) -> str:
        return self.text


@dataclass
class Question:
    """Everything a turn has to go on, in one timeline.

    `heard` and `typed` are (t_ms, text) pairs; `ago` turns them into words,
    because a model reasons about "forty seconds ago" far better than it does
    about an integer.
    """

    trigger: str = "pause"
    image: Path | None = None
    heard: list = None
    typed: list = None

    def happened(self, ago) -> str:
        lines = []
        if self.image is not None:
            lines.append(
                f"They have just written on your page by hand. The image at "
                f"{self.image} is a photograph of it, taken moments ago. Read "
                f"that file now, even if earlier pages in this conversation "
                f"look similar, and answer only what this one says."
            )
        else:
            lines.append(NO_PAGE)
        for when, text in self.heard or []:
            lines.append(f"Heard in the room, {ago(when)}: \"{text}\"")
        for when, text in self.typed or []:
            lines.append(f"Typed to you, {ago(when)}: \"{text}\"")
        return "\n\n".join(lines) + "\n"


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
                max_words=self.max_words,
                memory=self._memory_block(),
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

        reply = payload["result"]
        for note in REMEMBER.findall(reply):
            if self.memory is not None:
                self.memory.keep(note)
        reply = REMEMBER.sub("", reply)
        return Answer(
            text=" ".join(reply.split()),
            session_id=self.session_id,
            cost_usd=payload.get("total_cost_usd"),
            duration_ms=payload.get("duration_ms"),
        )

    def forget(self) -> None:
        """Drop the conversation. What was written to memory survives this."""
        self.session_id = ""
        self.session_file.unlink(missing_ok=True)
