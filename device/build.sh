#!/usr/bin/env bash
# Cross-compile the device agent and push it to the tablet.
# musl + static so the binary drops onto the reMarkable's minimal rootfs with
# no library expectations at all.
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p bin

zig cc -target arm-linux-musleabihf \
    -O2 -static -Wall -Wextra \
    -o bin/riddled device/riddled.c

ssh rm2 'mkdir -p /home/root/riddle'
scp -q bin/riddled rm2:/home/root/riddle/riddled
ssh rm2 'chmod +x /home/root/riddle/riddled'
echo "deployed $(ls -lh bin/riddled | awk '{print $5}') to rm2:/home/root/riddle/riddled"
