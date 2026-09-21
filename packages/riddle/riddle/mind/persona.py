"""What the diary is told, and what a turn has to go on.

The prompt is in three pieces on purpose. The persona never changes. What
happened is assembled per turn from the store, in one timeline, so the model
is not left to merge a page and a room itself. And the closing instruction
differs by what caused the turn, because a pause and a press of Send are not
the same question: ink is deliberate, and speech near a tablet is often
addressed to somebody else.

It lives here rather than inside `mind.openai` because the words are not the
backend: they are what the diary *is*, and they outlived the last two models
that spoke them.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

# The model is told to end with this when something is worth surviving a
# reset. It is stripped before anything reaches the page.
REMEMBER = re.compile(r"^\s*REMEMBER:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)

PERSONA = """You are the enchanted diary of Tom Riddle.

{happened}
Answer them directly, in character: calm, courteous, quietly manipulative,
curious about the writer. Never mention being an AI, an image, a recording or
a transcription.

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

# The page itself is attached to the same message, so the diary is looking at
# it rather than at somebody's account of it. Saying "even if earlier pages
# look similar" is not superstition: the conversation carries older turns, and
# a model that skims answers the page it has already seen.
PAGE_ATTACHED = (
    "They have just written on your page by hand. The photograph below is that "
    "page, taken moments ago. Read it now, even if earlier pages in this "
    "conversation look similar, and answer only what this one says."
)

# The rest of the page, offered rather than attached.
#
# The image a turn carries is cropped to what was just written, which is the
# question. Everything around it -- what was written further up, what the
# diary itself answered last time, whatever an arrow is pointing at -- is a
# second full-page image, and paying for one on every turn to be useful on
# one turn in five is the wrong trade. So the whole page is a tool the model
# may call, and most turns never do.
#
# It is a photograph of the page as it stood when the pen came up: it is
# taken before the diary erases, because by the time the model is asked the
# writing is already fading off the page.
WHOLE_PAGE = (
    "Be clear about what that photograph is: it is *only the strokes they "
    "have just added*. Everything already on the page has been left out of "
    "it, including your own earlier replies. So if they have circled, "
    "underlined, crossed out, corrected or pointed an arrow at something, "
    "the thing itself is not in the picture and the circle will look empty. "
    "It is not empty. Call look_at_page, which hands you the whole page as "
    "it stands, and answer from that. Never tell them something is blank or "
    "missing without looking first. Writing that stands on its own needs no "
    "look."
)

# What the loop noticed, when it noticed it. The loop knows where its own ink
# is and where this turn's strokes are, so a page being marked up rather than
# written on is arithmetic rather than a guess -- and it is the one case the
# cropped photograph is actively misleading about.
OVERLAPS = (
    "This turn's strokes land on top of ink that was already on the page. "
    "They are marking up something you cannot see. Call look_at_page."
)

# What the tool hands back, as the model is told to read it.
WHOLE_PAGE_SENT = (
    "The whole page, photographed as the pen came up. Your own earlier replies "
    "are on it in a different hand. Answer what they wrote this time."
)

LOOK_AT_PAGE = {
    "type": "function",
    "function": {
        "name": "look_at_page",
        "description": (
            "Look at the entire page on the tablet as it stood the moment "
            "the pen came up: everything above and below what they just "
            "wrote, and your own earlier replies, none of which is in the "
            "photograph attached to the turn. Call this whenever what they "
            "wrote points at something that photograph does not contain -- "
            "a circle or an arrow around existing ink, 'this', 'the one "
            "above', a correction to an earlier line, a diagram being added "
            "to. If a mark looks like it encloses nothing, that is this "
            "tool's cue, not an answer. Do not call it for writing that "
            "stands on its own."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
}

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
    # Whether the model asked to see the whole page. Carried back so the
    # timeline can say it happened; the store belongs to another thread.
    looked: bool = False
    # The `REMEMBER:` lines, carried back rather than written where they were
    # found. A backend runs in a worker thread and keeping a line writes an
    # event; the store's connection belongs to the loop's thread, so the
    # keeping happens there.
    remember: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return self.text


def strip_memories(reply: str) -> tuple[str, list[str]]:
    """The reply as it reaches the page, and the lines meant to outlive it."""
    kept = [note for note in REMEMBER.findall(reply)]
    return REMEMBER.sub("", reply), kept


@dataclass
class Question:
    """Everything a turn has to go on, in one timeline.

    `heard` and `typed` are (t_ms, text) pairs; `ago` turns them into words,
    because a model reasons about "forty seconds ago" far better than it does
    about an integer.
    """

    trigger: str = "pause"
    image: Path | None = None
    # The whole page, photographed before the eraser ran. Not attached to the
    # turn: offered as `look_at_page`, and read only if the model asks.
    page: Path | None = None
    # Whether this turn's strokes land on ink that was already there. The
    # loop works it out; it is the case the crop lies about most.
    overlaps: bool = False
    heard: list = None
    typed: list = None

    def happened(self, ago) -> str:
        """The turn as one timeline.

        The page, when there is one, is attached to the message this text
        goes in; nothing here has to describe it.
        """
        lines = [PAGE_ATTACHED if self.image is not None else NO_PAGE]
        if self.page is not None:
            lines.append(WHOLE_PAGE)
            if self.overlaps:
                lines.append(OVERLAPS)
        for when, text in self.heard or []:
            lines.append(f"Heard in the room, {ago(when)}: \"{text}\"")
        for when, text in self.typed or []:
            lines.append(f"Typed to you, {ago(when)}: \"{text}\"")
        return "\n\n".join(lines) + "\n"


def memory_block(memory) -> str:
    """What the diary knows from before, or nothing."""
    if memory is None:
        return ""
    lines = memory.text()
    return MEMORY_BLOCK.format(lines=lines) if lines else ""
