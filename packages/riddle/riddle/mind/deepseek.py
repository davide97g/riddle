"""Ask DeepSeek what the diary writes back.

Chosen for speed. A reply of twenty words arrives in about a second, which is
what a diary that answers a pause needs; the pen then takes longer to write it
than the model took to think it. It is also cheap enough that the cost of a
turn stops being a thing worth watching.

Three things follow from it not being Claude Code, and all three are handled
here rather than leaking into the loop:

- **It cannot see.** `riddle.mind.eyes` reads the page first and the
  description goes into the prompt where the file path would have gone.
- **It has no tools**, so the persona is not told it may search the web. A
  model promised a tool it does not have will answer as though it had used it.
- **It remembers nothing.** The conversation is a list of messages kept here
  and written to `var/chat.json`, so it survives a restart the way the resumed
  Claude Code session did. `forget()` deletes the file, which is what turning
  the page has always meant.

The API is OpenAI-shaped and spoken to with `urllib`. One POST with a json
body does not justify a dependency, and the one thing that would -- retrying
politely -- is not wanted here either: a diary that answers a pause is stale
within seconds, so a failed turn is better than a late one.
"""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from riddle.mind import eyes
from riddle.mind.persona import (
    CLOSING,
    PERSONA,
    Answer,
    Question,
    memory_block,
    strip_memories,
)

# How much of the conversation is carried forward. Each turn is a short reply
# and a page's worth of description, so this is a few thousand tokens at the
# outside -- enough that the diary remembers the thread, small enough that it
# stays fast and cannot grow without bound.
HISTORY = 24


class Diary:
    """One conversation with the diary, kept here rather than by the model."""

    def __init__(
        self,
        *,
        key: str,
        model: str,
        url: str,
        max_words: int,
        eyes_model: str,
        chat_file: Path,
        memory=None,
    ) -> None:
        self.key = key
        self.model = model
        self.url = url.rstrip("/")
        self.max_words = max_words
        self.eyes_model = eyes_model
        self.chat_file = chat_file
        self.memory = memory
        self.history = self._load()

    # --- the conversation ------------------------------------------------

    def _load(self) -> list[dict]:
        try:
            kept = json.loads(self.chat_file.read_text())
        except (OSError, ValueError):
            return []
        return kept if isinstance(kept, list) else []

    def _save(self) -> None:
        self.history = self.history[-HISTORY:]
        self.chat_file.parent.mkdir(parents=True, exist_ok=True)
        self.chat_file.write_text(json.dumps(self.history))

    def forget(self) -> None:
        """Drop the conversation. What was written to memory survives this."""
        self.history = []
        self.chat_file.unlink(missing_ok=True)

    # --- a turn ----------------------------------------------------------

    def _system(self) -> str:
        # The memory goes in every time rather than only on the first turn:
        # the system message is rebuilt per request and is not part of the
        # history, so a first-turn-only block would simply vanish afterwards.
        return PERSONA.format(
            happened="",
            search="",
            max_words=self.max_words,
            memory=memory_block(self.memory, first_turn=True),
            closing="",
        )

    def _page(self, image: Path | None) -> str:
        """What the page says, or nothing if it could not be read.

        A page the eyes could not read must not cost the turn: whatever was
        said or typed is still a question, and the diary answering that is
        better than an error where a reply should be.
        """
        if image is None:
            return ""
        try:
            began = time.monotonic()
            said = eyes.read_page(image, self.eyes_model)
            print(f"read the page in {time.monotonic() - began:.1f}s", file=sys.stderr)
            return said
        except Exception as exc:  # noqa: BLE001 - never lose a turn to the eyes
            print(f"could not read the page: {exc}", file=sys.stderr)
            return ""

    def reply_to(self, question, ago=None, timeout: int = 120) -> Answer | None:
        """Ask, and get back the reply.

        `ago` renders a session-relative timestamp as words; the store owns
        that, and passing it keeps this module from importing the store.
        """
        if isinstance(question, Path):  # the old shape: an image and nothing else
            question = Question(image=question)
        ago = ago or (lambda t_ms: "a moment ago")
        page = self._page(question.image)
        asked = (
            question.happened(ago, page=page)
            + "\n"
            + CLOSING.get(question.trigger, CLOSING["pause"])
        )

        began = time.monotonic()
        reply = self._post(
            [
                {"role": "system", "content": self._system()},
                *self.history,
                {"role": "user", "content": asked},
            ],
            timeout=timeout,
        )
        took_ms = int((time.monotonic() - began) * 1000)

        # The page description is the bulky half of the prompt and says
        # nothing the reply does not already answer, so what is kept is the
        # turn as the writer would recognise it.
        self.history += [
            {"role": "user", "content": asked},
            {"role": "assistant", "content": reply},
        ]
        self._save()

        reply, kept = strip_memories(reply)
        return Answer(
            text=" ".join(reply.split()), duration_ms=took_ms, remember=kept
        )

    def _post(self, messages: list[dict], timeout: int) -> str:
        if not self.key:
            raise RuntimeError(
                "no DeepSeek key: put RIDDLE_DEEPSEEK_KEY in .env, or set "
                "RIDDLE_MIND=claude"
            )
        body = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                # The page holds a couple of dozen words. Anything longer is
                # a model that has forgotten the constraint, and paying for
                # tokens that would be cut before they reached the pen.
                "max_tokens": 300,
                "temperature": 1.0,
                "stream": False,
            }
        ).encode()
        request = urllib.request.Request(
            f"{self.url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as answer:
                payload = json.loads(answer.read())
        except urllib.error.HTTPError as exc:
            # The body says which of the dozen reasons it was -- a dead key,
            # no balance, a rate limit -- and none of it echoes the key back.
            detail = exc.read().decode("utf-8", "replace").strip()[:400]
            raise RuntimeError(f"deepseek {exc.code}: {detail or exc.reason}") from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"deepseek unreachable: {exc.reason}") from None

        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("deepseek returned no reply")
        return (choices[0].get("message") or {}).get("content", "").strip()
