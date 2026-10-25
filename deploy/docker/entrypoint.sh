#!/bin/sh
# Bring up a riddle server in a container: the loop in the background, the
# page in the foreground, so the container lives and dies with the page.
#
# Inside here nobody supervises the loop but the page itself -- there is no
# systemd -- so `riddle.process.manager` says `here`, and the book on the page
# starts and stops it exactly as it would on a laptop.
set -eu
cd /app

if [ -z "${RIDDLE_WEB_PASSWORD:-}" ] && [ "${RIDDLE_ALLOW_NO_PASSWORD:-}" != "1" ]; then
    echo "RIDDLE_WEB_PASSWORD is empty, and this container listens on every interface." >&2
    echo "Set one, or RIDDLE_ALLOW_NO_PASSWORD=1 if something else guards the port." >&2
    exit 64
fi

# ssh refuses a key it thinks others can read, and a bind mount keeps the
# host's owner and mode. So the mounted directory is copied, not used.
if [ -d /ssh ]; then
    mkdir -p /root/.ssh && cp -R /ssh/. /root/.ssh/ && chmod 700 /root/.ssh \
        && chmod 600 /root/.ssh/* 2>/dev/null || true
fi

model="${RIDDLE_ASR_MODEL:-ggml-parakeet-tdt-0.6b-v3-q8_0.bin}"
case "$model" in /*) ;; *) model="/data/models/$model" ;; esac
if [ ! -f "$model" ] && [ "${RIDDLE_FETCH_MODEL:-1}" = "1" ]; then
    echo "fetching the speech model once, 640 MB, into $model"
    mkdir -p "$(dirname "$model")"
    curl -fL --retry 3 -o "$model.part" \
        "https://huggingface.co/ggml-org/parakeet-GGUF/resolve/main/$(basename "$model")" \
        && mv "$model.part" "$model" || echo "no speech model: the microphone stays off" >&2
fi

if [ "${RIDDLE_DEMO:-}" = "1" ]; then
    riddle demo seed || true
fi
if [ "${RIDDLE_START_DIARY:-1}" = "1" ]; then
    riddle diary start || echo "the diary did not start; the page will say why" >&2
fi
exec riddle voice start --foreground
