# apps/apple

The native client: the same two pages as [apps/web](../web/README.md) — the
diary and Live — as one SwiftUI app for macOS and iOS. It talks to the same
voice server over the same http and sockets, and like the page it never
touches the tablet: anything that wants ink leaves an intent for the loop.

## Build it

```bash
brew install xcodegen                 # once
cd apps/apple
xcodegen generate                     # project.yml -> Riddle.xcodeproj
open Riddle.xcodeproj                 # or build from the shell:

xcodebuild -scheme Riddle -destination 'platform=macOS' -derivedDataPath build build
xcodebuild -scheme Riddle -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build
```

`Riddle.xcodeproj` and `Riddle/Info.plist` are generated and gitignored;
`project.yml` is the project. The Mac build is signed ad hoc, so it runs from
a clone with no Apple account. An iPhone needs a team: set it in Xcode under
Signing, or pass `DEVELOPMENT_TEAM=...` to `xcodebuild`.

For other Macs, `./package.sh` builds `build/Riddle-<version>.dmg`: signed
with the Developer ID, notarized and stapled. It needs a notarytool profile
called `riddle`; the script's header says how to store one.

The icon is `Riddle/AppIcon.icon`, an Icon Composer document whose one layer
`icon/make_icon.py` draws: the wordmark's own strokes, bent round a circle.
Rerun it after changing the word or the bend, and look at the result with
`ictool` rather than guessing; the script's header has the command.

Xcode 27 and the 26 SDKs, Swift 6 with the main actor as the default
isolation. The two things off it are the audio tap (`AudioPipe`) and the wire
types, which say so.

## Connect it

The first screen asks for the server and its password:

- the address `riddle voice start` prints — `127.0.0.1:8765` on the same Mac;
- a LAN or tailnet address, plain http. App Transport Security is off for
  exactly this, because the address is typed in and there is no list of
  domains to except;
- the tunnel's `https://` url.

The password is `RIDDLE_WEB_PASSWORD`, or nothing when the server has no gate.
It is never stored: the app mints the cookie from it the way
`riddle/web/auth.py` does, `hmac(password, "riddle-v1")`, checks it against
`/api/state`, and keeps only that, in the keychain. Settings (⌘, on the Mac,
the gear on the iPhone) changes or forgets it.

A microphone, unlike on the web, needs no https: the permission is the app's.

## What is where

| | |
|---|---|
| `Riddle/Wire/Protocol.swift` | the wire, a hand-written mirror of [docs/protocols.md](../../docs/protocols.md). `riddle check` holds it to the event kinds and to every message the server sends |
| `Riddle/Wire/Server.swift` | the address and the cookie, the http calls, the keychain |
| `Riddle/Wire/EventsSocket.swift` | `/ws/events`: `hello {since}` on every dial, a ping every fifteen seconds, jittered backoff |
| `Riddle/Model/Diary.swift` | the reducer, the same as `apps/web/src/state/reducer.ts`, and the provider's actions |
| `Riddle/Model/LiveFeed.swift` | `/ws/live` |
| `Riddle/Model/Microphone.swift` | `AVAudioEngine` to 16 kHz int16 mono, 200 ms frames numbered little-endian, on `/ws/audio` |
| `Riddle/Model/Snapshots.swift` | the shelf: up to ten pngs in Application Support |
| `Riddle/Views/` | everything on screen. `Rows.swift` renders one row per event kind, and is checked for it |

## The rules it keeps

The same ones as the page, for the same reasons; each is written out where it
is kept.

- **Live hangs up whenever it is not on screen.** An open `/ws/live` is
  somebody watching as far as the diary knows, and it keeps its hands off the
  page for as long as one is. So the feed opens only while the Live tab is
  showing and the app is not in the background.
- **A recording is never reconnected.** A dropped audio socket ends the
  recording with a toast; a gap would be stitched into a sentence nobody
  said. Frames past eight in flight are dropped rather than queued.
- **Nothing is queued while offline.** A send made while the socket is down
  is marked not delivered, never sent later onto whatever page is open then.
- **Starting and stopping the diary is not optimistic.** The book changes
  when the server says the loop's heartbeat arrived.

What it keeps on the device is in [docs/privacy.md](../../docs/privacy.md).
