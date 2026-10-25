"""`riddle setup`: one walk through everything a new server needs.

The project grew on one Mac and one mini PC, set up by hand, with the reasons
written into docs/deploy.md afterwards. That is a fine way to build a thing
and a bad way to hand it to somebody: every step is in there, but in the
order it was discovered rather than the order it has to be done. This is the
order it has to be done, asked one question at a time, and every step can be
skipped and run again later. Nothing is written until it has been asked for,
and the only thing changed on the tablet is an ssh key appended to root's
`authorized_keys` and, if you say so, ssh over wifi switched on.

It never draws. The agent is put on the tablet (that is a file, not ink),
and the check at the end is `riddle doctor`, which reads and does not write.

The long form of every step, with what to do when it fails, is
docs/self-hosting.md.
"""

import getpass
import secrets
import shlex
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from riddle import config, paths

ENV = paths.ROOT / ".env"
KEY = Path.home() / ".ssh" / "id_ed25519_riddle"
SSH_CONFIG = Path.home() / ".ssh" / "config"
USB = "10.11.99.1"
MODEL_URL = (
    "https://huggingface.co/ggml-org/parakeet-GGUF/resolve/main/"
    "ggml-parakeet-tdt-0.6b-v3-q8_0.bin"
)
DOCS = "docs/self-hosting.md"



# --- asking ---------------------------------------------------------------


def say(text: str = "") -> None:
    print(text, flush=True)


def step(n: int, title: str) -> None:
    say()
    say(f"── {n}. {title}")


def ask(question: str, default: str = "") -> str:
    shown = f" [{default}]" if default else ""
    try:
        answer = input(f"{question}{shown}: ").strip()
    except EOFError:
        answer = ""
    return answer or default


def yes(question: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    answer = ask(f"{question} ({hint})").lower()
    if not answer:
        return default
    return answer.startswith("y")


def secret(question: str) -> str:
    try:
        return getpass.getpass(f"{question}: ").strip()
    except EOFError:
        return ""


# --- .env -----------------------------------------------------------------


def write_env(values: dict[str, str]) -> None:
    """Set some keys in .env, keeping every other line as it was.

    A line that sets a key already is replaced where it stands, so a file
    somebody has annotated keeps its comments; anything new goes at the end.
    The file is chmod 600 after, because it holds an API key and the page's
    password, and `riddle config --check` complains otherwise.
    """
    lines = ENV.read_text().splitlines() if ENV.exists() else []
    left = dict(values)
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip().removeprefix("export ").strip()
        if key in left and not line.lstrip().startswith("#"):
            out.append(f"{key}={_quote(left.pop(key))}")
        else:
            out.append(line)
    out += [f"{key}={_quote(value)}" for key, value in left.items()]
    ENV.write_text("\n".join(out) + "\n")
    ENV.chmod(0o600)
    names = ", ".join(values)
    say(f"   wrote {names} to .env")


def _quote(value: str) -> str:
    return f'"{value}"' if any(c in value for c in " #'\"") else value


# --- ssh ------------------------------------------------------------------


def _ssh(host: str, command: str, *, batch: bool = True, timeout: float = 20.0,
         stdin: str | None = None):
    argv = ["ssh", "-o", "ConnectTimeout=6", "-o", "StrictHostKeyChecking=accept-new"]
    if batch:
        argv += ["-o", "BatchMode=yes"]
    argv += [host, command]
    try:
        return subprocess.run(argv, input=stdin, capture_output=batch, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return None


def has_alias(alias: str) -> bool:
    if not SSH_CONFIG.exists():
        return False
    for line in SSH_CONFIG.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].lower() == "host" and alias in parts[1:]:
            return True
    return False


def add_alias(alias: str, address: str) -> None:
    """An ssh alias for the tablet: root, this key, nothing else offered.

    `IdentitiesOnly` because dropbear on the tablet counts every key an agent
    offers as a failed attempt, and a laptop with five keys loaded is locked
    out before it reaches the right one.
    """
    SSH_CONFIG.parent.mkdir(mode=0o700, exist_ok=True)
    block = (
        f"\n# Added by `riddle setup`: the reMarkable.\n"
        f"Host {alias}\n"
        f"    HostName {address}\n"
        f"    User root\n"
        f"    IdentityFile {KEY}\n"
        f"    IdentitiesOnly yes\n"
        f"    ServerAliveInterval 15\n"
    )
    with SSH_CONFIG.open("a") as fh:
        fh.write(block)
    SSH_CONFIG.chmod(0o600)
    say(f"   added Host {alias} -> {address} to {SSH_CONFIG}")


def ensure_key() -> bool:
    if KEY.exists():
        return True
    done = subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "riddle", "-f", str(KEY)],
        capture_output=True, text=True,
    )
    if done.returncode:
        say(f"   ssh-keygen failed: {done.stderr.strip()}")
        return False
    say(f"   made a key for the tablet: {KEY}")
    return True


def copy_key(address: str) -> bool:
    """Append this key to root's authorized_keys, with the password once.

    ssh asks for the password on the terminal itself, so this works over a
    pipe without the password ever passing through here.
    """
    pub = KEY.with_suffix(".pub").read_text().strip()
    command = (
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && "
        f"(grep -qxF {shlex.quote(pub)} ~/.ssh/authorized_keys || "
        f"echo {shlex.quote(pub)} >> ~/.ssh/authorized_keys) && "
        "chmod 600 ~/.ssh/authorized_keys"
    )
    say("   the tablet's root password is under Settings > Help > Copyrights and licenses")
    done = subprocess.run([
        "ssh", "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=accept-new",
        "-o", "PubkeyAuthentication=no", "-o", "PreferredAuthentications=password,keyboard-interactive",
        f"root@{address}", command,
    ])
    return done.returncode == 0


def machine(alias: str) -> str | None:
    done = _ssh(alias, "cat /sys/devices/soc0/machine")
    if done is None or done.returncode:
        return None
    return done.stdout.strip()


# --- the steps ------------------------------------------------------------


def tablet(found: dict) -> None:
    say("The server talks to the tablet over ssh, as root, with a key of its own.")
    say(f"Plugged in by USB the tablet is {USB}; on wifi it is the address under")
    say("Settings > Help > Copyrights and licenses, below the password.")
    address = ask("Tablet address", USB)
    alias = ask("ssh alias for it", "rm2" if address == USB else "rm2-wifi")
    if not ensure_key():
        return
    if not has_alias(alias):
        add_alias(alias, address)
    else:
        say(f"   {alias} is already in {SSH_CONFIG}; using it as it is")

    if machine(alias) is None:
        say(f"   {alias} does not let this key in yet; adding it")
        if not copy_key(address):
            say(f"   could not log in to root@{address}. See {DOCS}#the-tablet")
            return
    model = machine(alias)
    if model is None:
        say(f"   still no answer from {alias} with the key. See {DOCS}#the-tablet")
        return
    # The doctor's lists, not a second copy: docs/tablets.md is their home.
    from riddle.doctor import EXPERIMENTAL, SUPPORTED

    status = ("supported" if model in SUPPORTED
              else "experimental" if model in EXPERIMENTAL else "unsupported")
    say(f"   {alias} answers: {model} ({status})")
    if status == "unsupported":
        say("   This tablet is not one riddle can drive: the pen, the screen and the")
        say("   processor are different. docs/tablets.md says what differs.")
        found["unsupported"] = True
        return
    if status == "experimental":
        say("   The reMarkable 1 shares the pen digitizer but has never been tested.")
        say("   Expect to calibrate it: docs/tablets.md.")
    found["alias"] = alias
    found["address"] = address
    write_env({"RM2_SSH_HOST": alias})

    if address == USB and yes("Turn on ssh over wifi, so the server need not be cabled to it?"):
        wifi(alias, found)


WIFI = (
    # The vendor's own switch where the firmware has one, and the marker its
    # wlan socket checks where it does not. Either way, then the address.
    "if command -v rm-ssh-over-wlan >/dev/null 2>&1; then rm-ssh-over-wlan on; else "
    "mkdir -p /home/root/.config/remarkable && "
    "touch /home/root/.config/remarkable/rm_enable_ssh_wifi_marker && "
    "systemctl restart dropbear-wlan.socket 2>/dev/null; fi; "
    "ip -4 -o addr show wlan0 | awk '{print $4}' | cut -d/ -f1"
)


def wifi(usb_alias: str, found: dict) -> None:
    done = _ssh(usb_alias, WIFI)
    address = (done.stdout.strip().splitlines() or [""])[-1] if done else ""
    if not address:
        say("   the tablet has no wifi address: is wifi on? Skipping.")
        return
    alias = "rm2-wifi"
    if not has_alias(alias):
        add_alias(alias, address)
    if machine(alias) is None:
        say(f"   ssh over wifi to {address} does not answer yet. Firmware differs here;")
        say(f"   {DOCS}#ssh-over-wifi has the manual way. Keeping the USB route.")
        return
    say(f"   {alias} ({address}) answers. Reserve that address on your router:")
    say("   it is DHCP, and the alias points at nothing the day it changes.")
    found["alias"] = alias
    write_env({"RM2_SSH_HOST": alias, "RM2_WIFI_HOST": address})


def agent(found: dict) -> None:
    alias = found.get("alias")
    if not alias:
        say("   no tablet yet, so nothing to put on it. Later: riddle device build")
        return
    if not shutil.which("zig"):
        say("   zig is not installed; it cross-compiles the agent. Install it")
        say("   (brew install zig, or ziglang.org/download) and run: riddle device build")
        return
    if yes(f"Build the agent and copy it to {alias}? (a file, not ink)"):
        subprocess.run([str(paths.ROOT / "riddle"), "device", "build", "--host", alias])


def mind() -> None:
    cfg = config.get()
    say("The diary's replies come from a model that can see the page: OpenAI by")
    say("default, or anything OpenAI-compatible (RIDDLE_OPENAI_URL).")
    if cfg.openai_key and not yes("A key is already set. Replace it?", default=False):
        return
    key = secret("OpenAI API key (empty to skip)")
    if key:
        write_env({"RIDDLE_OPENAI_KEY": key})


def page(found: dict) -> None:
    cfg = config.get()
    say("The page, and the iPhone and Mac app, sign in with one password.")
    if cfg.web_password and not yes("A password is already set. Replace it?", default=False):
        found["password"] = "(the one in .env)"
    else:
        typed = secret("Password for the page (empty makes one up)")
        password = typed or secrets.token_urlsafe(12)
        write_env({"RIDDLE_WEB_PASSWORD": password})
        found["password"] = password
    say()
    say("Live shows the tablet's screen on the phone, and lets the diary look at")
    say("the whole page. It works by reading the screen out of the tablet's memory,")
    say("so it is its own switch.")
    if yes("Turn on Live?", default=bool(cfg.allow_snap)):
        write_env({"RIDDLE_ALLOW_SNAP": "1"})


def client() -> None:
    if (paths.ROOT / "apps" / "web" / "dist" / "index.html").exists():
        say("   the page is built")
        return
    if not shutil.which("bun"):
        say("   bun is not installed, so the page is not built (the app still works).")
        say("   Install bun (bun.sh) and run: riddle web install && riddle web build")
        return
    if yes("Build the page you open in a browser?"):
        launcher = str(paths.ROOT / "riddle")
        subprocess.run([launcher, "web", "install"])
        subprocess.run([launcher, "web", "build"])


def ears() -> None:
    model = config.get().asr_model
    if not shutil.which("parakeet-cli"):
        say("   parakeet-cli is not installed, so the microphone is off. On a Mac:")
        say("   brew install whisper.cpp. On Linux it is built: "
            f"{DOCS}#the-microphone")
    if model.is_file():
        say(f"   the speech model is there ({model.stat().st_size >> 20} MB)")
        return
    if not yes(f"Download the speech model ({MODEL_URL.rsplit('/', 1)[-1]}, 640 MB)?"):
        return
    model.parent.mkdir(parents=True, exist_ok=True)
    partial = model.with_suffix(".part")

    def progress(blocks: int, size: int, total: int) -> None:
        if total > 0:
            done = min(100, blocks * size * 100 // total)
            print(f"\r   {done}%", end="", flush=True)

    try:
        urllib.request.urlretrieve(MODEL_URL, partial, progress)
    except OSError as exc:
        say(f"\n   download failed: {exc}")
        partial.unlink(missing_ok=True)
        return
    partial.rename(model)
    say(f"\n   saved {paths.relative(model)}")


def services(found: dict) -> None:
    from riddle import units

    which = units.kind()
    if which is None:
        say("   no systemd or launchd here: run `riddle start`, or use deploy/docker.")
        return
    names = ["voice", "diary"] if found.get("alias") else ["voice"]
    if yes(f"Run {' and '.join(names)} under {which}, so they start at boot?"):
        units.install(names)


def reach(found: dict) -> None:
    port = config.get().web_port
    say("The app and the page need to reach this server. Three ways, from most")
    say("private to most public; the long form is in " + f"{DOCS}#reaching-it.")
    say()
    say("  1. Tailscale (recommended): your devices only, with a real certificate.")
    say("     riddle voice share     prints https://<this-machine>.<tailnet>.ts.net")
    say(f"  2. Your LAN only: set RIDDLE_WEB_HOST=0.0.0.0 in .env, then the app")
    say(f"     connects to http://<this machine's address>:{port}")
    say("  3. A Cloudflare tunnel to a domain of yours: reachable from anywhere,")
    say("     guarded by the password alone.")
    if yes("Make it reachable on your LAN now (option 2)?", default=False):
        write_env({"RIDDLE_WEB_HOST": "0.0.0.0"})
        found["lan"] = True


def finish(found: dict) -> None:
    say()
    say("── done")
    if found.get("password"):
        say(f"   password for the app and the page: {found['password']}")
    say("   restart the halves to pick up .env:  riddle start  (or riddle service install)")
    say("   then check it all:                   riddle doctor")
    say("   then, before anything draws, take a backup:  riddle backup create")


def run(args) -> int:
    if sys.platform not in ("darwin",) and not sys.platform.startswith("linux"):
        say("riddle runs on Linux or macOS. On Windows, inside WSL.")
        return 1
    say("riddle setup. Every step can be skipped and run again later; nothing")
    say("draws on the tablet. The long form is " + DOCS + ".")
    found: dict = {}
    steps = [
        ("The tablet", lambda: tablet(found)),
        ("The agent on the tablet", lambda: agent(found)),
        ("The model", mind),
        ("The password, and Live", lambda: page(found)),
        ("The page in a browser", client),
        ("The microphone", ears),
        ("Reaching it", lambda: reach(found)),
        ("Starting at boot", lambda: services(found)),
    ]
    only = getattr(args, "only", None)
    for n, (title, fn) in enumerate(steps, 1):
        if only and only.lower() not in title.lower():
            continue
        step(n, title)
        fn()
        # Each step reads what the one before it wrote.
        config.load()
        if found.get("unsupported"):
            return 1
    finish(found)
    if not only and found.get("alias") and yes("Run riddle doctor now?"):
        return subprocess.run([str(paths.ROOT / "riddle"), "doctor"]).returncode
    return 0
