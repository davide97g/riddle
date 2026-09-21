"""Ask a model that can see the page what the diary writes back.

One call per turn, with the photograph of what was just written attached to
it -- and a second one only if the model asks to see the rest of the page,
which is a tool it may call and mostly does not. There used to be two -- a vision model describing the page in words, and a blind model
answering the description -- and that split existed only because the model
that answered could not see. It cost a second, a second API key, and the half
of a page that survives being turned into prose: an arrow's direction, a word
crossed out, which of two things was circled.

A small model on purpose. The reply is at most a couple of dozen words and
has to arrive before the pause stops feeling like one, so the cheapest model
that can read handwriting is the right one; `gpt-4.1-mini` is the default and
`RIDDLE_OPENAI_MODEL` is how you disagree.

The conversation is kept here rather than by the API, in `var/chat.json`, so
it survives a restart -- and only the *words* of each turn are kept. Carrying
every page image forward would make each turn cost more than the last for
nothing: the reply already says what the page said.

Spoken to with `urllib`. One POST with a json body does not justify a
dependency, and the one thing that would -- retrying politely -- is not
wanted: a diary that answers a pause is stale within seconds, so a failed
turn is better than a late one.
"""

import base64
import json
import mimetypes
import time
import urllib.error
import urllib.request
from pathlib import Path

from riddle.mind.persona import (
    CLOSING,
    LOOK_AT_PAGE,
    PERSONA,
    WHOLE_PAGE_SENT,
    Answer,
    Question,
    memory_block,
    strip_memories,
)

# How much of the conversation is carried forward. Each turn is a short reply
# and a short question, so this stays a few thousand tokens at the outside --
# enough that the diary remembers the thread, small enough that it cannot
# grow without bound.
HISTORY = 24

# How many times one turn may ask to see the whole page. One: the page does
# not change while the turn runs, so a second look would photograph nothing
# new, and every look is a full-page image and a round trip the writer is
# sitting there waiting for.
LOOKS = 1


class Diary:
    """One conversation with the diary, kept here rather than by the model."""

    def __init__(
        self,
        *,
        key: str,
        model: str,
        url: str,
        max_words: int,
        chat_file: Path,
        memory=None,
    ) -> None:
        self.key = key
        self.model = model
        self.url = url.rstrip("/")
        self.max_words = max_words
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
            max_words=self.max_words,
            memory=memory_block(self.memory),
            closing="",
        )

    def reply_to(self, question, ago=None, timeout: int = 120) -> Answer | None:
        """Ask, and get back the reply.

        `ago` renders a session-relative timestamp as words; the store owns
        that, and passing it keeps this module from importing the store.
        """
        if isinstance(question, Path):  # the old shape: an image and nothing else
            question = Question(image=question)
        ago = ago or (lambda t_ms: "a moment ago")
        asked = (
            question.happened(ago)
            + "\n"
            + CLOSING.get(question.trigger, CLOSING["pause"])
        )

        began = time.monotonic()
        reply, looked = self._converse(
            [
                {"role": "system", "content": self._system()},
                *self.history,
                {"role": "user", "content": _with_page(asked, question.image)},
            ],
            page=question.page,
            timeout=timeout,
        )
        took_ms = int((time.monotonic() - began) * 1000)

        # The page is not kept, and neither is the look at the whole page if
        # there was one: an image in the history would be paid for on every
        # later turn, and what it said is in the reply already.
        self.history += [
            {"role": "user", "content": asked},
            {"role": "assistant", "content": reply},
        ]
        self._save()

        reply, kept = strip_memories(reply)
        return Answer(
            text=" ".join(reply.split()),
            duration_ms=took_ms,
            remember=kept,
            looked=looked,
        )

    def _converse(self, messages: list[dict], page, timeout: int) -> tuple[str, bool]:
        """The turn, and the one look at the whole page it is allowed.

        The tool is offered only when there is a page to hand back, and the
        offer is withdrawn once it has been taken, so the loop cannot run
        more than twice however the model answers.

        A `tool` message cannot carry an image -- the role takes text -- so
        the tool says the page follows and the page follows as a user
        message. That is the shape every provider documents for this, and it
        is why the reply has to come from a third message rather than the
        second.
        """
        looked = 0
        while True:
            offer = [LOOK_AT_PAGE] if page is not None and looked < LOOKS else None
            message = self._post(messages, tools=offer, timeout=timeout)
            calls = message.get("tool_calls") or []
            reply = (message.get("content") or "").strip()
            if not calls:
                if not reply:
                    raise RuntimeError("openai returned no reply")
                return reply, bool(looked)
            looked += 1
            messages.append(message)
            # Every call gets an answer even if the model asked twice in one
            # message: an unanswered tool_call_id is a 400 on the next post.
            for call in calls:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": "The whole page follows as an image.",
                    }
                )
            messages.append(
                {"role": "user", "content": _with_page(WHOLE_PAGE_SENT, page)}
            )

    def _post(self, messages: list[dict], timeout: int, tools=None) -> dict:
        if not self.key:
            raise RuntimeError(
                "no OpenAI key: put RIDDLE_OPENAI_KEY in .env"
            )
        asked = {
            "model": self.model,
            "messages": messages,
            # The page holds a couple of dozen words. Anything longer is a
            # model that has forgotten the constraint, and paying for tokens
            # that would be cut before they reached the pen.
            "max_tokens": 300,
            "temperature": 1.0,
            "stream": False,
        }
        if tools:
            asked["tools"] = tools
        body = json.dumps(asked).encode()
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
            # no balance, a rate limit, a model that cannot see -- and none of
            # it echoes the key back.
            detail = exc.read().decode("utf-8", "replace").strip()[:400]
            raise RuntimeError(f"openai {exc.code}: {detail or exc.reason}") from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"openai unreachable: {exc.reason}") from None

        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("openai returned no reply")
        # The whole message rather than its text: a turn that asks to see the
        # page puts nothing in `content` and everything in `tool_calls`.
        return choices[0].get("message") or {}


def _with_page(asked: str, image: Path | None):
    """The turn, with the page attached to it if there is one.

    A data URI rather than a link, because the only copy of that page is on
    this disk and publishing one to fetch it would be a worse idea than the
    extra kilobytes. `detail: high` is not optional: handwriting is exactly
    the thing a downscaled tile loses.
    """
    if image is None:
        return asked
    try:
        raw = Path(image).read_bytes()
    except OSError:
        return asked      # a page that vanished must not cost the turn
    kind = mimetypes.guess_type(str(image))[0] or "image/png"
    data = base64.b64encode(raw).decode()
    return [
        {"type": "text", "text": asked},
        {
            "type": "image_url",
            "image_url": {"url": f"data:{kind};base64,{data}", "detail": "high"},
        },
    ]
