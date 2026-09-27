import SwiftUI

/// The native client: the same two pages as apps/web, the diary and Live,
/// talking to the same voice server over the same http and sockets. It
/// never touches the tablet itself -- nothing here does but the loop.
@main
struct RiddleApp: App {
    @State private var connection = Connection()
    @State private var diary = Diary()
    @State private var toasts = Toasts()
    @State private var snapshots = Snapshots()
    @State private var microphone = Microphone()
    @State private var outbox = Outbox()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(connection)
                .environment(diary)
                .environment(toasts)
                .environment(snapshots)
                .environment(microphone)
                .environment(outbox)
        }
        #if os(macOS)
        .defaultSize(width: 760, height: 860)
        .commands {
            CommandGroup(replacing: .newItem) {}
        }
        #endif

        #if os(macOS)
        Settings {
            ServerSettings()
                .environment(connection)
                .environment(diary)
                .frame(width: 440)
                .padding(20)
        }
        #endif
    }
}
