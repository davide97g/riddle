#!/usr/bin/env bash
# Start, stop and check the page you speak into.
#
# Same shape as diary.sh, and for the same reason: the interface is a phone,
# not this terminal, so the server belongs in the background with a pidfile
# and a log you can tail.
#
#   ./voice.sh start     bring the page up
#   ./voice.sh stop      take it down
#   ./voice.sh status    is it up, and on which port
#   ./voice.sh log       follow what it is doing
#   ./voice.sh share     put a real certificate in front of it, for a phone
#   ./voice.sh restart   stop, then start
set -euo pipefail
cd "$(dirname "$0")"

PIDFILE=".voice.pid"
LOGFILE="voice.log"

running() {
    [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null
}

start() {
    if running; then
        echo "already up (pid $(cat "$PIDFILE"))"
        return 0
    fi
    [ -f .env ] || { echo "no .env: copy .env.example and fill it in" >&2; exit 1; }

    set -a; source .env; set +a
    : > "$LOGFILE"
    ./.venv/bin/python host/voice.py >>"$LOGFILE" 2>&1 &
    echo $! > "$PIDFILE"

    sleep 2
    if ! running; then
        rm -f "$PIDFILE"
        echo "failed to start:" >&2
        tail -n 15 "$LOGFILE" >&2
        exit 1
    fi
    tail -n 5 "$LOGFILE"
}

stop() {
    if ! running; then
        rm -f "$PIDFILE"
        echo "not running"
        return 0
    fi
    pid=$(cat "$PIDFILE")
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.25
    done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
    rm -f "$PIDFILE"
    echo "stopped"
}

case "${1:-status}" in
    start)   start ;;
    stop)    stop ;;
    restart) stop; start ;;
    status)
        if running; then
            echo "up (pid $(cat "$PIDFILE"))"
            tail -n 3 "$LOGFILE" 2>/dev/null || true
        else
            echo "not running"
        fi
        ;;
    log)     tail -f "$LOGFILE" ;;
    share)
        # A browser will not give a page the microphone unless it is a secure
        # context, and a lan address over http is not one. Tailscale holds a
        # real certificate for this machine's tailnet name and proxies to
        # loopback, so nothing here has to grow an ssl import.
        set -a; [ -f .env ] && source .env; set +a
        port="${RIDDLE_WEB_PORT:-8765}"
        tailscale serve --bg "$port"
        echo "open https://$(tailscale status --json | sed -n 's/.*"DNSName": *"\([^"]*\)\..*/\1/p' | head -n1).$(tailscale status --json | sed -n 's/.*"MagicDNSSuffix": *"\([^"]*\)".*/\1/p' | head -n1)/ on your phone"
        echo "take it down again with: tailscale serve reset"
        ;;
    *)       echo "usage: $0 {start|stop|restart|status|log|share}" >&2; exit 2 ;;
esac
