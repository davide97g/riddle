"""Ask Claude Code, in print mode, what the diary writes back."""

import json
import subprocess
from pathlib import Path

PERSONA = """You are the enchanted diary of Tom Riddle. Someone has just
written on your page by hand. The image at {image} is a photograph of their
handwriting, taken moments ago.

Read that file now, even if earlier pages in this conversation look similar,
and answer only what this one says.

Read what they wrote, then answer them directly, in character: calm, courteous,
quietly manipulative, curious about the writer. Never mention being an AI, an
image, or a transcription.

Hard constraints on your reply:
- at most {max_words} words; a curt line is as welcome as a full sentence
- wrap at most two words in *asterisks* when you want them to land harder
- plain ASCII only: no quotes, dashes, emoji or accents
- output the reply text alone, with no preamble or explanation

The page renders a short reply in a cursive hand and a longer one in a plainer
one, so let the length follow what you actually mean to say.
"""


class Diary:
    """One conversation with the diary, resumed across turns."""

    def __init__(self, model: str, max_words: int, session_file: Path) -> None:
        self.model = model
        self.max_words = max_words
        self.session_file = session_file
        self.session_id = (
            session_file.read_text().strip() if session_file.exists() else ""
        )

    def reply_to(self, image: Path, timeout: int = 120) -> str:
        cmd = [
            "claude",
            "-p",
            PERSONA.format(image=image, max_words=self.max_words),
            "--model",
            self.model,
            "--output-format",
            "json",
            "--allowedTools",
            "Read",
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
        return " ".join(payload["result"].split())

    def forget(self) -> None:
        self.session_id = ""
        self.session_file.unlink(missing_ok=True)
