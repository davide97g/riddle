"""Catch the documentation lying, mechanically.

Most of what rots in a document cannot be checked by a program. Three things
can: the list of settings, the list of event kinds, and the list of
websocket messages. Each of those exists in one place in the code and is
mirrored in two or three others, and each mirror has drifted before -- the
README's copy of the agent protocol was missing a third of its lines by the
time anyone noticed.

So this greps the code for the source of truth and diffs it against the
mirrors. An env table that polices itself is the difference between docs
that stay true and docs that were true once.
"""

import re

from riddle import config, paths


def _text(*parts) -> str:
    path = paths.ROOT.joinpath(*parts)
    return path.read_text() if path.is_file() else ""


def settings() -> list[str]:
    """Every declared setting appears in the generated files, and vice versa."""
    problems = list(config.check())
    declared = {s.name for s in config.SETTINGS}

    doc = _text("docs", "configuration.md")
    for name in sorted(declared - set(re.findall(r"`(RIDDLE_\w+|RM2_\w+)`", doc))):
        problems.append(f"docs/configuration.md does not mention {name}")

    # Anything reading the environment directly is a setting that escaped the
    # declaration, and will end up with a second default somewhere.
    for path in sorted((paths.PACKAGE).rglob("*.py")):
        if path.name in ("config.py", "paths.py", "check.py"):
            continue
        for found in re.findall(r'environ(?:\.get)?\(\s*"(RIDDLE_\w+|RM2_\w+)"', path.read_text()):
            if found not in declared:
                problems.append(f"{path.name} reads {found}, which config.py does not declare")
            else:
                problems.append(f"{path.name} reads {found} directly instead of through config")
    return problems


def kinds() -> list[str]:
    """The event kinds the store allows are the ones the page can render."""
    from riddle.store.db import KINDS

    problems = []
    protocol = _text("apps", "web", "src", "lib", "protocol.ts")
    match = re.search(r"export type EventKind =([^\n]*(?:\n\s*\|[^\n]*)*)", protocol)
    on_page = set(re.findall(r"'(\w+)'", match.group(1))) if match else set()
    for kind in sorted(set(KINDS) - on_page):
        problems.append(f"protocol.ts has no EventKind {kind!r}")
    for kind in sorted(on_page - set(KINDS)):
        problems.append(f"protocol.ts declares EventKind {kind!r}, which the store rejects")

    timeline = _text("apps", "web", "src", "components", "Timeline.tsx")
    rendered = set(re.findall(r"case '(\w+)':", timeline))
    for kind in sorted(on_page - rendered):
        problems.append(f"Timeline.tsx renders no row for {kind!r}")

    doc = _text("docs", "store.md")
    for kind in sorted(k for k in KINDS if f"`{k}`" not in doc):
        problems.append(f"docs/store.md does not describe the {kind!r} kind")
    return problems


def messages() -> list[str]:
    """Every message the server sends is one the client knows how to read."""
    problems = []
    server = _text("packages", "riddle", "riddle", "web", "server.py")
    sent = set(re.findall(r'"type":\s*"([\w.]+)"', server))
    sent |= set(re.findall(r'"type": "([\w.]+)"', _text("packages", "riddle", "riddle", "voice", "ears.py")))

    protocol = _text("apps", "web", "src", "lib", "protocol.ts")
    known = set(re.findall(r"type:\s*'([\w.]+)'", protocol))
    for message in sorted(sent - known):
        problems.append(f"the server sends {message!r}, which protocol.ts does not declare")

    doc = _text("docs", "protocols.md")
    for message in sorted(m for m in sent if m not in doc):
        problems.append(f"docs/protocols.md does not document {message!r}")
    return problems


def run(args=None) -> int:
    problems = settings() + kinds() + messages()
    for problem in problems:
        print(problem)
    if not problems:
        print("the docs and the code agree")
    return 1 if problems else 0
