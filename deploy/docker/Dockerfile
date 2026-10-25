# riddle's server in a container: both halves, the page, and the microphone.
#
# The author's own server runs without one (docs/deploy.md says why: the loop
# holds an ssh pipe to a device on the LAN, and a container adds a network to
# cross and a key to mount). This exists for two other cases. A server that is
# a NAS or anything else that only runs containers. And a demo server --
# RIDDLE_DEMO=1, no tablet, no key -- where being sealed off from the host is
# the point rather than a cost.
#
# Built from the repository root:
#
#   docker build -f deploy/docker/Dockerfile -t riddle .
#
# deploy/docker/README.md has the volumes, the environment and the ssh key.

# --- the speech binary ------------------------------------------------------
# whisper.cpp publishes no Linux binaries, so it is built here, statically,
# for the reason docs/deploy.md gives: a shared build links by rpath into a
# tree this stage throws away, and the microphone would break silently.
FROM debian:bookworm-slim AS ears
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential cmake git ca-certificates && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch v1.9.1 https://github.com/ggml-org/whisper.cpp /src
WORKDIR /src
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
      -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_SERVER=OFF -DGGML_NATIVE=OFF \
 && cmake --build build -j"$(nproc)" --target parakeet-cli \
 && install -m755 build/bin/parakeet-cli /usr/local/bin/parakeet-cli

# --- the page -----------------------------------------------------------------
FROM oven/bun:1.3 AS page
WORKDIR /app/apps/web
COPY apps/web/package.json apps/web/bun.lock ./
RUN bun install --frozen-lockfile
COPY apps/web ./
RUN bun run build

# --- the server ---------------------------------------------------------------
FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
      openssh-client tini curl ca-certificates libgomp1 procps && rm -rf /var/lib/apt/lists/*
COPY --from=ears /usr/local/bin/parakeet-cli /usr/local/bin/parakeet-cli

WORKDIR /app
# The two files riddle.paths looks for to find its checkout, then the package.
COPY .env.example riddle taps.json ./
COPY packages/riddle packages/riddle
COPY device device
RUN python -m venv .venv && .venv/bin/pip install --no-cache-dir -e packages/riddle
COPY --from=page /app/apps/web/dist apps/web/dist
COPY deploy/docker/entrypoint.sh /usr/local/bin/riddle-entrypoint

# Everything the diary writes goes to the volume: the store, the photographs,
# the recordings, the speech model. The checkout stays read-only in spirit.
ENV RIDDLE_VAR=/data \
    RIDDLE_WEB_HOST=0.0.0.0 \
    PATH=/app/.venv/bin:$PATH
VOLUME /data
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8765/api/health || exit 1
ENTRYPOINT ["/usr/bin/tini", "--", "riddle-entrypoint"]
