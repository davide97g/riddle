"""Read the page out, for a diary that cannot see it.

The mind that answers may have no eyes. DeepSeek does not take images at all,
so the capture is handed to a small vision model first and what comes back is
a description of the page, which goes into the prompt where the file path used
to go.

Two things this is not. It is not a transcription: a page of a notebook holds
arrows, boxes, charts, crossings out and drawings as often as it holds words,
and a reader that returns only the words throws away half of what was asked.
And it is not an answer: this model describes and stops, because the diary is
the thing with the persona and a describer that starts answering would put two
voices on one page.

It is deliberately the cheapest model that can see. The diary's own reply is
at most a couple of dozen words; the cost that matters is here, once per page.
"""

import json
import subprocess

PROMPT = """Read this page of a paper notebook and describe everything on it.

The image at {path} is a photograph of it, taken moments ago. Read that file
now, and describe only that page.

It may hold handwriting, arrows, boxes, tables, charts, sketches, diagrams,
crossings out, or any mixture of those. Report, in this order:

- every word of handwriting, verbatim, in reading order
- everything drawn: what each mark or figure depicts, and where on the page
  it sits
- how the parts connect: what an arrow runs from and to, what a label belongs
  to, what is circled, boxed, underlined or struck through
- any numbers, axes, units or table cells, exactly as they are written

Describe what is there, not what it means. Do not answer anything the page
asks, do not give advice, and do not add anything that is not on the page. If
a mark is illegible or ambiguous, say so rather than guessing at it. Be brief
on a bare page and thorough on a busy one.
"""


def read_page(image, model: str, timeout: int = 90) -> str:
    """What is on the page, in words. Raises if the reader fails outright."""
    done = subprocess.run(
        [
            "claude",
            "-p",
            PROMPT.format(path=image),
            "--model",
            model,
            "--output-format",
            "json",
            "--allowedTools",
            "Read",
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip() or "the page could not be read")
    payload = json.loads(done.stdout)
    if payload.get("is_error"):
        raise RuntimeError(payload.get("result", "the page could not be read"))
    # Kept as it came back, line breaks and all: the layout of the answer is
    # part of what it says about the layout of the page.
    return str(payload.get("result", "")).strip()
