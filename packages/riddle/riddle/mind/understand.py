"""Read a page and say what is on it, for somebody looking at it.

The diary answers a page in its own voice, a couple of dozen words it can
write back in ink. This is the other thing a model can do with the same
photograph: read it out and explain it -- the handwriting as text, what the
drawing is, which box an arrow points at -- for a person at a screen, where
there is room for more than a sentence and no pen to wait on.

Asked for as json with a strict schema rather than as prose, so the page can
lay the parts out instead of printing a paragraph. One call, no history, no
tools: each page is understood on its own.

Its own model, `RIDDLE_UNDERSTAND_MODEL`, because the two jobs want different
ones. The diary wants the cheapest thing that can read handwriting before a
pause stops feeling like one; this wants the model that reads it best, and a
person who pressed a button can wait three seconds.
"""

import base64
import json
import time
import urllib.error
import urllib.request

SYSTEM = """\
You read photographs of handwritten pages from a reMarkable 2 e-ink tablet
and explain them to the person who wrote them.

The photograph is the whole screen. Ignore the tablet's own interface: a row
of tool icons along the top edge, and any page counter or menu. Only what
was written or drawn on the page matters.

Read everything that is written. Keep the writer's own words and line breaks
in the transcript; mark a word you cannot read with [?] rather than
guessing. Explain structure the way a careful reader would: what a heading
covers, what an arrow connects, what is boxed, circled, crossed out or
grouped by a bracket, and what small icons beside items seem to mean.

Answer in the language the page is written in. Be specific to this page and
do not pad: no advice, no praise, nothing that is not on the page."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "kind", "summary", "points", "transcript"],
    "properties": {
        "title": {
            "type": "string",
            "description": "A few words naming what the page is.",
        },
        "kind": {
            "type": "string",
            "enum": ["notes", "list", "diagram", "sketch", "maths", "letter", "mixed", "blank"],
        },
        "summary": {
            "type": "string",
            "description": "One to three sentences: what the page is about.",
        },
        "points": {
            "type": "array",
            "description": "What the structure says, one observation each: "
                           "groupings, connections, emphasis, symbols.",
            "items": {"type": "string"},
        },
        "transcript": {
            "type": "string",
            "description": "Everything written, as text, in reading order, "
                           "with line breaks. Empty if nothing is written.",
        },
    },
}


def understand(png: bytes, *, key: str, model: str, url: str, timeout: int = 90) -> dict:
    """What the model makes of one page, as the schema's fields plus timing."""
    if not key:
        raise RuntimeError("no OpenAI key: put RIDDLE_OPENAI_KEY in .env")
    asked = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is on this page?"},
                    {
                        # `high`, as for the diary: handwriting is exactly
                        # what a downscaled tile loses.
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64," + base64.b64encode(png).decode(),
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "page", "strict": True, "schema": SCHEMA},
        },
        # Room for a dense page's transcript and whatever the model spends
        # reasoning first. `max_tokens` is refused by the newer models.
        "max_completion_tokens": 6000,
    }
    request = urllib.request.Request(
        f"{url.rstrip('/')}/chat/completions",
        data=json.dumps(asked).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    began = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            payload = json.loads(answer.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace").strip()[:400]
        raise RuntimeError(f"openai {exc.code}: {detail or exc.reason}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"openai unreachable: {exc.reason}") from None

    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    if message.get("refusal"):
        raise RuntimeError(f"the model would not read it: {message['refusal']}")
    if choice.get("finish_reason") == "length":
        raise RuntimeError("the page was too much to read in one answer")
    try:
        read = json.loads(message.get("content") or "")
    except ValueError:
        raise RuntimeError("openai returned something that was not the page") from None
    return {
        **read,
        "model": payload.get("model", model),
        "took_ms": int((time.monotonic() - began) * 1000),
    }
