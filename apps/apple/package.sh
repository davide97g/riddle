#!/usr/bin/env bash
# Build the Mac app for other Macs: signed with a Developer ID, in a dmg,
# notarized and stapled so Gatekeeper opens it offline.
#
#   apps/apple/package.sh            # -> apps/apple/build/Riddle-<version>.dmg
#
# Needs the Developer ID certificate in the keychain and a notarytool
# profile, stored once with:
#
#   xcrun notarytool store-credentials riddle --apple-id <apple id> --team-id DA596D32QB
set -euo pipefail

TEAM="${DEVELOPMENT_TEAM:-DA596D32QB}"
IDENTITY="${IDENTITY:-Developer ID Application: Davide Ghiotto ($TEAM)}"
PROFILE="${NOTARY_PROFILE:-riddle}"

cd "$(dirname "$0")"
xcodegen generate >/dev/null

# CODE_SIGN_INJECT_BASE_ENTITLEMENTS=NO, or Xcode adds get-task-allow -- a
# debugger's entitlement -- and the notary refuses the app outright.
xcodebuild -project Riddle.xcodeproj -scheme Riddle -destination 'platform=macOS' \
  -derivedDataPath build -configuration Release \
  DEVELOPMENT_TEAM="$TEAM" CODE_SIGN_STYLE=Manual CODE_SIGN_IDENTITY="$IDENTITY" \
  OTHER_CODE_SIGN_FLAGS=--timestamp CODE_SIGN_INJECT_BASE_ENTITLEMENTS=NO \
  clean build | grep -E "error:|BUILD" || true

APP=build/Build/Products/Release/Riddle.app
codesign --verify --deep --strict "$APP"
VERSION=$(plutil -extract CFBundleShortVersionString raw "$APP/Contents/Info.plist")
DMG="build/Riddle-$VERSION.dmg"

rm -rf build/dmg "$DMG"
mkdir -p build/dmg/stage
cp -R "$APP" build/dmg/stage/
ln -s /Applications build/dmg/stage/Applications
hdiutil create -volname Riddle -srcfolder build/dmg/stage -ov -format UDZO "$DMG" >/dev/null
codesign --sign "$IDENTITY" --timestamp "$DMG"

xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait --timeout 15m
xcrun stapler staple "$DMG"
spctl -a -vv -t open --context context:primary-signature "$DMG"
echo "$DMG"
