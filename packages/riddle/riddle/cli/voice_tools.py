"""`riddle asr`: the speech model, and whether it is telling the truth."""

from pathlib import Path


def add(sub) -> None:
    asr = sub.add_parser("asr", help="the speech model")
    verbs = asr.add_subparsers(dest="verb", metavar="<verb>")

    check = verbs.add_parser(
        "check", help="time a transcription and verify its segment units"
    )
    check.add_argument("clip", type=Path, help="a wav whose length you know")
    check.set_defaults(run=_check)

    model = verbs.add_parser("model", help="where the model is expected, and whether it is there")
    model.set_defaults(run=_model)

    asr.set_defaults(run=_model)


def _check(args) -> int:
    from riddle.tools import asr_check

    return asr_check.run(args)


def _model(args) -> int:
    from riddle import config

    path = config.get().asr_model
    if path.is_file():
        print(f"{path} ({path.stat().st_size // (1024 * 1024)}M)")
        return 0
    print(f"no speech model at {path}")
    print("the page still runs without one; the microphone is simply off.")
    return 1
