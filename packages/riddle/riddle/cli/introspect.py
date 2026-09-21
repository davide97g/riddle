"""`riddle config` and `riddle doctor`: what is set, and what is wrong."""


def add(sub) -> None:
    conf = sub.add_parser("config", help="every setting, its value and where it came from")
    shape = conf.add_mutually_exclusive_group()
    shape.add_argument("--json", action="store_true", help="as json")
    shape.add_argument("--env", action="store_true", help="as dotenv, for `env $(...)`")
    shape.add_argument("--example", action="store_true", help="print .env.example")
    shape.add_argument("--check", action="store_true", help="only what is wrong with it")
    shape.add_argument(
        "--write-example", action="store_true", help="regenerate .env.example in place"
    )
    conf.set_defaults(run=_config)

    check = sub.add_parser("check", help="check the docs against the code")
    check.set_defaults(run=_check_docs)

    doc = sub.add_parser("doctor", help="check everything this project needs to work")
    doc.add_argument("--quick", action="store_true", help="skip anything that touches the tablet")
    doc.add_argument("--json", action="store_true")
    doc.add_argument("--only", default=None, metavar="GROUP", help="one group of checks")
    doc.set_defaults(run=_doctor)


def _config(args) -> int:
    import json

    from riddle import config, paths

    cfg = config.get()

    if args.example or args.write_example:
        text = config.as_example()
        if args.write_example:
            (paths.ROOT / ".env.example").write_text(text)
            print("wrote .env.example")
            return 0
        print(text, end="")
        return 0

    if args.check:
        problems = config.check()
        for problem in problems:
            print(problem)
        return 1 if problems else 0

    values = {}
    for setting in config.SETTINGS:
        if setting.manual:
            continue
        value = getattr(cfg, setting.attr)
        values[setting.name] = "<set>" if setting.secret else value

    if args.json:
        print(json.dumps({k: str(v) for k, v in values.items()}, indent=2))
        return 0
    if args.env:
        for name, value in values.items():
            print(f"{name}={value}")
        return 0

    width = max(len(name) for name in values)
    section = None
    for setting in config.SETTINGS:
        if setting.manual:
            continue
        if setting.section != section:
            section = setting.section
            print(f"\n  {config.SECTION_TITLES[section]}")
        source = cfg.sources.get(setting.name, "default")
        print(f"  {setting.name:<{width}}  {values[setting.name]}  ({source})")
    return 0


def _check_docs(args) -> int:
    from riddle import check

    return check.run(args)


def _doctor(args) -> int:
    import json

    from riddle import doctor

    results = doctor.run_checks(only=args.only, quick=args.quick)
    if args.json:
        print(json.dumps([r.__dict__ for r in results], indent=2))
    else:
        print(doctor.report(results))
        bad = sum(1 for r in results if r.status == doctor.FAIL)
        warn = sum(1 for r in results if r.status == doctor.WARN)
        print(f"\n  {len(results)} checks, {bad} failed, {warn} warned")
    return 1 if any(r.status == doctor.FAIL for r in results) else 0
