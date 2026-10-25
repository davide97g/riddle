#!/usr/bin/env bash
# The App Store screenshots, from a demo server with invented pages -- never
# from the real diary.
#
#   apps/apple/screenshots.sh                 # iPhone 6.9" and iPad 13", light and dark, and setup
#   apps/apple/screenshots.sh mac shot.png    # frame a Mac window capture to 2880x1800
#
# The first form starts a passwordless RIDDLE_DEMO container on :8798 (built
# from deploy/docker, so docker is needed), makes two clean simulators of its
# own so nothing of yours is on screen, and writes var/appstore/screenshots/.
# A Mac window is captured by hand (Shift-Cmd-5, a window, Option to drop the
# shadow) with the app opened as:
#   open apps/apple/build/Build/Products/Debug/Riddle.app --args -riddle.server http://127.0.0.1:8798/
set -euo pipefail
cd "$(dirname "$0")"
ROOT=$(cd ../.. && pwd)
OUT="$ROOT/var/appstore/screenshots"
mkdir -p "$OUT"

if [ "${1:-}" = mac ]; then
  "$ROOT/.venv/bin/python" - "$2" "$OUT/mac-diary.png" <<'PY'
import sys
from PIL import Image
shot = Image.open(sys.argv[1]).convert("RGBA")
W, H = 2880, 1800
shot.thumbnail((W - 240, H - 160))
page = Image.new("RGBA", (W, H), (236, 233, 226, 255))
page.alpha_composite(shot, ((W - shot.width) // 2, (H - shot.height) // 2))
page.convert("RGB").save(sys.argv[2])
print(sys.argv[2])
PY
  exit 0
fi

PORT=8798
docker build -q -f "$ROOT/deploy/docker/Dockerfile" -t riddle "$ROOT" >/dev/null
docker rm -f riddle-shots >/dev/null 2>&1 || true
docker run -d --name riddle-shots -p $PORT:8765 -e RIDDLE_DEMO=1 \
  -e RIDDLE_ALLOW_NO_PASSWORD=1 -e RIDDLE_FETCH_MODEL=0 riddle >/dev/null
trap 'docker rm -f riddle-shots >/dev/null 2>&1 || true' EXIT
sleep 8

xcodegen generate >/dev/null
xcodebuild -scheme Riddle -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build | grep -E "error:|BUILD" || true
APP=build/Build/Products/Debug-iphonesimulator/Riddle.app

sim() {  # name, device type
  local id
  id=$(xcrun simctl list devices | awk -v n="$1" '$0 ~ n" \\(" {gsub(/[()]/,"",$(NF-1)); print $(NF-1); exit}')
  [ -n "$id" ] || id=$(xcrun simctl create "$1" "$2")
  xcrun simctl boot "$id" 2>/dev/null || true
  xcrun simctl bootstatus "$id" -b >/dev/null
  echo "$id"
}

shoot() {  # simulator id, file prefix
  local D=$1 P=$2
  until xcrun simctl install "$D" "$APP" 2>/dev/null; do sleep 3; done
  xcrun simctl status_bar "$D" override --time 9:41 --batteryState charged \
    --batteryLevel 100 --wifiBars 3 --cellularBars 4
  for look in light dark; do
    xcrun simctl ui "$D" appearance $look
    xcrun simctl terminate "$D" com.davide97g.riddle 2>/dev/null || true
    xcrun simctl launch "$D" com.davide97g.riddle -riddle.server "http://127.0.0.1:$PORT/" >/dev/null
    sleep 7
    xcrun simctl io "$D" screenshot "$OUT/$P-diary-$look.png" >/dev/null 2>&1
  done
  xcrun simctl ui "$D" appearance light
  xcrun simctl terminate "$D" com.davide97g.riddle
  xcrun simctl spawn "$D" defaults delete com.davide97g.riddle riddle.server 2>/dev/null || true
  xcrun simctl launch "$D" com.davide97g.riddle >/dev/null
  sleep 6
  xcrun simctl io "$D" screenshot "$OUT/$P-setup.png" >/dev/null 2>&1
}

shoot "$(sim riddle-shots-iphone 'iPhone 17 Pro Max')" iphone-6.9
shoot "$(sim riddle-shots-ipad 'iPad Pro 13-inch (M5)')" ipad-13
ls -1 "$OUT"
