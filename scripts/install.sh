#!/usr/bin/env bash
# Install riddle's server on this machine, then walk through `riddle setup`.
#
#   curl -fsSL https://raw.githubusercontent.com/davide97g/riddle/main/scripts/install.sh | bash
#
# What it does, and nothing else:
#   1. clones the repository into $RIDDLE_DIR (default ~/riddle), or pulls it
#      if it is already there;
#   2. makes .venv with Python 3.13+ and installs the package into it --
#      with uv, which it installs into ~/.local/bin if there is no Python
#      3.13 here and no uv either;
#   3. runs `riddle setup`, which asks before it does anything.
# No sudo, nothing outside $RIDDLE_DIR, ~/.local/bin and (in setup, if you
# say yes) ~/.ssh and your user's services. docs/self-hosting.md is the long form.
set -euo pipefail

DIR="${RIDDLE_DIR:-$HOME/riddle}"
REPO="${RIDDLE_REPO:-https://github.com/davide97g/riddle.git}"
say() { printf '\033[1m%s\033[0m\n' "$*"; }

case "$(uname -s)" in
  Linux|Darwin) ;;
  *) echo "riddle's server runs on Linux or macOS (on Windows, inside WSL 2)." >&2; exit 1 ;;
esac
command -v git >/dev/null || { echo "git is needed: install it and run this again." >&2; exit 1; }
command -v ssh >/dev/null || { echo "ssh is needed: install openssh-client and run this again." >&2; exit 1; }

if [ -d "$DIR/.git" ]; then
  say "updating $DIR"
  git -C "$DIR" pull --ff-only
else
  say "cloning riddle into $DIR"
  git clone --depth 1 "$REPO" "$DIR"
fi
cd "$DIR"

has_python() {
  local py
  for py in python3.14 python3.13 python3; do
    if command -v "$py" >/dev/null &&
       "$py" -c 'import sys; sys.exit(sys.version_info < (3, 13))' 2>/dev/null; then
      echo "$py"; return 0
    fi
  done
  return 1
}

export PATH="$HOME/.local/bin:$PATH"
if [ ! -x .venv/bin/riddle ]; then
  if command -v uv >/dev/null || ! PY=$(has_python); then
    if ! command -v uv >/dev/null; then
      say "no Python 3.13 here: installing uv to fetch one (~/.local/bin)"
      curl -LsSf https://astral.sh/uv/install.sh | sh
    fi
    say "making .venv"
    uv venv --python 3.13 .venv
    uv pip install --python .venv/bin/python -e packages/riddle
  else
    say "making .venv with $PY"
    "$PY" -m venv .venv
    .venv/bin/pip install -q -e packages/riddle
  fi
fi

say "riddle is installed in $DIR. Now the questions."
# Piped from curl, this script's stdin is the script: setup reads the terminal.
if (exec </dev/tty) 2>/dev/null; then
  exec ./riddle setup </dev/tty
else
  echo "no terminal to ask in: run $DIR/riddle setup"
fi
