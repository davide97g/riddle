#!/usr/bin/env bash
# Archive the app for the App Store, for the iPhone/iPad and for the Mac, and
# upload both builds to App Store Connect. One app record holds both
# platforms (same bundle id, universal purchase).
#
#   apps/apple/release.sh             # archive and export both: build/release/
#   apps/apple/release.sh --upload    # archive, then upload both to App Store Connect
#   apps/apple/release.sh --upload ios   # or one platform
#
# Signing is automatic, with the team below. Two ways to be allowed to upload:
#   - Xcode > Settings > Accounts signed in with the Apple ID of the team; or
#   - an App Store Connect API key (Users and Access > Integrations), in
#     ASC_KEY_ID, ASC_ISSUER_ID and ASC_KEY_PATH (the .p8 file).
# The Mac's distribution certificate is created by Xcode on the first export
# (-allowProvisioningUpdates); nothing needs making by hand.
#
# The build number is the time, so every run is higher than the last without
# anything to remember. The marketing version is MARKETING_VERSION in
# project.yml. apps/apple/AppStore.md is the rest of the submission.
set -euo pipefail

TEAM="${DEVELOPMENT_TEAM:-DA596D32QB}"
BUILD="${BUILD_NUMBER:-$(date -u +%Y%m%d%H%M)}"
UPLOAD=0
PLATFORMS=()
for arg in "$@"; do
  case "$arg" in
    --upload) UPLOAD=1 ;;
    ios|macos) PLATFORMS+=("$arg") ;;
    *) echo "usage: $0 [--upload] [ios] [macos]" >&2; exit 64 ;;
  esac
done
[ ${#PLATFORMS[@]} -eq 0 ] && PLATFORMS=(ios macos)

cd "$(dirname "$0")"
xcodegen generate >/dev/null
OUT=build/release
mkdir -p "$OUT"

AUTH=()
if [ -n "${ASC_KEY_ID:-}" ]; then
  AUTH=(-authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID"
        -authenticationKeyPath "$ASC_KEY_PATH")
fi

OPTIONS="$OUT/ExportOptions.plist"
cat > "$OPTIONS" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>method</key><string>app-store-connect</string>
  <key>destination</key><string>$([ $UPLOAD = 1 ] && echo upload || echo export)</string>
  <key>teamID</key><string>$TEAM</string>
  <key>signingStyle</key><string>automatic</string>
  <key>manageAppVersionAndBuildNumber</key><false/>
  <key>uploadSymbols</key><true/>
</dict>
</plist>
PLIST

for platform in "${PLATFORMS[@]}"; do
  case "$platform" in
    ios) DEST='generic/platform=iOS' ;;
    macos) DEST='generic/platform=macOS' ;;
  esac
  ARCHIVE="$OUT/Riddle-$platform.xcarchive"
  echo "== $platform: archiving build $BUILD"
  # project.yml signs the Mac ad hoc so a clone builds with no account; the
  # store build is the team's, so the identity is put back to Xcode's choice.
  xcodebuild -project Riddle.xcodeproj -scheme Riddle -configuration Release \
    -destination "$DEST" -archivePath "$ARCHIVE" \
    DEVELOPMENT_TEAM="$TEAM" CODE_SIGN_STYLE=Automatic \
    "CODE_SIGN_IDENTITY[sdk=macosx*]=Apple Development" \
    CURRENT_PROJECT_VERSION="$BUILD" \
    -allowProvisioningUpdates ${AUTH[@]+"${AUTH[@]}"} \
    clean archive | grep -E "error:|warning: .*(Riddle/|entitlement)|ARCHIVE" || true
  [ -d "$ARCHIVE" ] || { echo "no archive for $platform" >&2; exit 1; }

  echo "== $platform: $([ $UPLOAD = 1 ] && echo uploading || echo exporting)"
  xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportPath "$OUT/$platform" \
    -exportOptionsPlist "$OPTIONS" -allowProvisioningUpdates ${AUTH[@]+"${AUTH[@]}"} \
    | grep -E "error:|EXPORT|Upload|upload" || true
done

echo "build $BUILD done. $([ $UPLOAD = 1 ] && echo 'App Store Connect processes it in ~15 min.' || echo "Files in apps/apple/$OUT; rerun with --upload to send them.")"
