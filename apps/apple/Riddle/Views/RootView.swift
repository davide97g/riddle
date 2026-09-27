import SwiftUI

/// Setup until a server has said yes, then the two pages.
struct RootView: View {
    @Environment(Connection.self) private var connection
    @Environment(Diary.self) private var diary
    @Environment(Toasts.self) private var toasts
    @Environment(\.scenePhase) private var phase

    enum Page: Hashable { case diary, live }
    @State private var page: Page = .diary

    var body: some View {
        Group {
            if connection.server == nil {
                SetupView()
            } else {
                TabView(selection: $page) {
                    Tab("Diary", systemImage: "book.pages", value: .diary) {
                        NavigationStack { DiaryView() }
                    }
                    Tab("Live", systemImage: "eye", value: .live) {
                        NavigationStack { LiveView(showing: page == .live && phase != .background) }
                    }
                }
                .tabViewStyle(.automatic)
                .libraryDrop()
            }
        }
        .overlay(alignment: .top) { ToastStack() }
        .onChange(of: connection.server, initial: true) { _, server in
            if let server { diary.start(server) } else { diary.stop() }
        }
        .onChange(of: phase) { _, now in
            // A phone backgrounds the app and the socket dies quietly.
            // Coming back should feel instant rather than waiting out the
            // backoff.
            if now == .active { diary.wake() }
        }
        .onChange(of: diary.failure) { _, said in
            guard let said else { return }
            toasts.failure("The server said no", said)
            diary.failure = nil
        }
    }
}
