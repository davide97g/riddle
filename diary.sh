#!/usr/bin/env bash
# Start, stop and check the diary loop.
#
# run.sh holds the terminal; this keeps the loop running in the background with
# a pidfile and a log, which is what you want when the tablet is the interface
# and the terminal is not.
#
#   ./diary.sh start     begin listening
#   ./diary.sh stop      stop listening
#   ./diary.sh status    is it running, and on which route
#   ./diary.sh log       follow what it is doing
#   ./diary.sh restart   stop, then start
set -euo pipefail
cd "$(dirname "$0")"

PIDFILE=".riddle.pid"
LOGFILE="riddle.log"

running() {
    [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null
}

start() {
    if running; then
        echo "already listening (pid $(cat "$PIDFILE"))"
        return 0
    fi
    [ -f .env ] || { echo "no .env: copy .env.example and fill it in" >&2; exit 1; }

    set -a; source .env; set +a
    : > "$LOGFILE"
    ./.venv/bin/python host/riddle.py >>"$LOGFILE" 2>&1 &
    echo $! > "$PIDFILE"

    # The loop fails early and loudly if the tablet is unreachable, so a moment
    # here is the difference between reporting "started" and reporting why not.
    sleep 3
    if ! running; then
        rm -f "$PIDFILE"
        echo "failed to start:" >&2
        tail -n 15 "$LOGFILE" >&2
        exit 1
    fi
    echo "listening (pid $(cat "$PIDFILE")) via ${RM2_SSH_HOST:-rm2}, log: $LOGFILE"
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
    # The loop holds an ssh pipe to the tablet; if it will not go down politely
    # that pipe stays open and the next start cannot have the digitizer.
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
            echo "listening (pid $(cat "$PIDFILE"))"
            tail -n 3 "$LOGFILE" 2>/dev/null || true
        else
            echo "not running"
        fi
        ;;
    log)     tail -f "$LOGFILE" ;;
    *)       echo "usage: $0 {start|stop|restart|status|log}" >&2; exit 2 ;;
esac
