"""The model, and the little the diary keeps when the conversation resets.

Two backends answer, and `open()` is the only place that chooses between
them. They share the words (`persona`) and the shape -- `reply_to(question)`
and `forget()` -- and nothing above this package knows which one is running.

- `deepseek`: fast and cheap, and the default. It cannot see, so `eyes` reads
  the page for it, and it has no web search.
- `llm`: Claude Code in print mode. It reads the capture itself and can search
  the web, at a few seconds and a few cents a turn.
"""

from riddle import paths


def open(cfg, memory=None):
    """The mind `RIDDLE_MIND` asks for, built from the configuration."""
    if cfg.mind == "claude":
        from riddle.mind.llm import Diary

        return Diary(
            model=cfg.model,
            max_words=cfg.max_words,
            session_file=paths.SESSION,
            memory=memory,
        )
    if cfg.mind != "deepseek":
        raise SystemExit(
            f"RIDDLE_MIND={cfg.mind!r}: it is 'deepseek' or 'claude'"
        )
    from riddle.mind.deepseek import Diary

    return Diary(
        key=cfg.deepseek_key,
        model=cfg.deepseek_model,
        url=cfg.deepseek_url,
        max_words=cfg.max_words,
        eyes_model=cfg.eyes_model,
        chat_file=paths.CHAT,
        memory=memory,
    )
