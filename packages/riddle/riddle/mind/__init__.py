"""The model, and the little the diary keeps when the conversation resets.

One backend now. It used to be two -- DeepSeek for the words with a Claude
Code subprocess reading the page for it, or Claude Code for both -- and the
whole arrangement existed because the model that answered could not see. One
that can collapses it into a single call, a single key, and no CLI to install
and log in on a machine nobody sits at.

`riddle.mind.openai` answers; `persona` holds the words, which outlived both
of the models that said them before; `memory` is the handful of lines that
survive a page turn.
"""

from riddle import paths


def open(cfg, memory=None):
    """The diary's mind, built from the configuration."""
    from riddle.mind.openai import Diary

    return Diary(
        key=cfg.openai_key,
        model=cfg.openai_model,
        url=cfg.openai_url,
        max_words=cfg.max_words,
        chat_file=paths.CHAT,
        memory=memory,
    )
