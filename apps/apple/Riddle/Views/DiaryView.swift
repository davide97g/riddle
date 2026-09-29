import SwiftUI

/// The main page: the timeline, what you can say to it, and the switches.
struct DiaryView: View {
    @Environment(Diary.self) private var diary
    @State private var settings = false
    @Environment(\.horizontalSizeClass) private var width

    var body: some View {
        Timeline()
            .safeAreaInset(edge: .top, spacing: 0) {
                if diary.conn == .closed {
                    Text("Not connected to the diary. Is `riddle voice start` running?")
                        .font(.callout)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .background(.bar)
                        .transition(.move(edge: .top).combined(with: .opacity))
                }
            }
            .safeAreaInset(edge: .bottom, spacing: 0) { Composer() }
            .animation(.snappy, value: diary.conn)
            .toolbar {
                if width != .compact {
                    ToolbarItem(placement: .principal) { Wordmark().frame(height: 18) }
                }
                ToolbarItemGroup(placement: .primaryAction) {
                    DiaryButton()
                    SendToTabletButton()
                    EraseButton()
                }
                ToolbarItem(placement: toolbarLeading) {
                    ConnectionBadge()
                }
                #if os(iOS)
                ToolbarItem(placement: .topBarLeading) {
                    PhoneMenu { settings = true }
                }
                #endif
            }
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            .sheet(isPresented: $settings) {
                NavigationStack {
                    ServerSettings()
                        .padding(20)
                        .frame(maxHeight: .infinity, alignment: .top)
                        .navigationTitle("Server")
                        .navigationBarTitleDisplayMode(.inline)
                        .toolbar {
                            ToolbarItem(placement: .cancellationAction) { Button("Close") { settings = false } }
                        }
                }
                .presentationDetents([.medium, .large])
            }
            #endif
    }

    private var toolbarLeading: ToolbarItemPlacement {
        #if os(iOS)
        .topBarLeading
        #else
        .navigation
        #endif
    }
}

/// Every row, in the order the room happened in.
struct Timeline: View {
    @Environment(Diary.self) private var diary
    /// Only follow if the reader is already at the bottom. Yanking the view
    /// out from under someone reading back is worse than a missed row.
    @State private var stick = true
    @State private var nearBottom = true
    @State private var tick = 0

    /// How long a `tool` row may go on claiming to be happening. Nothing
    /// marks the end of a turn, so motion also expires: long enough that a
    /// real reply is still being inked, short enough that an idle page is
    /// still.
    private static let liveMs = 60_000

    var body: some View {
        let rows = diary.inOrder
        let newest = rows.last?.id
        let freshTool: Bool = {
            _ = tick
            guard case let .event(e)? = rows.last, e.kind == .tool else { return false }
            return diary.nowMs - e.t_ms < Self.liveMs
        }()

        ScrollViewReader { scroller in
            ScrollView {
                LazyVStack(spacing: 12) {
                    if rows.isEmpty {
                        VStack(spacing: 12) {
                            Rectangle().fill(.primary.opacity(0.15)).frame(width: 96, height: 1)
                            Text("Nothing yet. Write on the tablet, or say something.")
                                .font(.callout)
                                .foregroundStyle(.secondary)
                                .multilineTextAlignment(.center)
                        }
                        .padding(.vertical, 64)
                    }
                    ForEach(rows) { row in
                        Group {
                            switch row {
                            case let .pending(p): PendingRowView(row: p)
                            case let .event(e):
                                EventRow(event: e, newest: row.id == newest, live: row.id == newest && freshTool)
                            }
                        }
                        .id(row.id)
                        .transition(.opacity.combined(with: .offset(y: 6)))
                    }
                    ForEach(diary.reading, id: \.self) { _ in
                        StatusLine(symbol: "waveform") { Text("reading that back") }
                    }
                    if diary.hearing, diary.reading.isEmpty {
                        StatusLine(symbol: "waveform") { Text("listening") }
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }
                .frame(maxWidth: 680)
                .padding(.horizontal, 16)
                .padding(.vertical, 16)
                .frame(maxWidth: .infinity)
                .animation(.snappy, value: rows.count)
            }
            .defaultScrollAnchor(.bottom)
            .onScrollGeometryChange(for: Bool.self) { geo in
                geo.contentSize.height - geo.contentOffset.y - geo.containerSize.height < 80
            } action: { _, near in
                nearBottom = near
            }
            // Only a scroll by hand decides whether to follow. Content that
            // grows under the reader -- a capture arriving after its row --
            // moves the bottom away without anybody having scrolled, and
            // must not count as reading back.
            .onScrollPhaseChange { old, now in
                if old != .idle, now == .idle { stick = nearBottom }
            }
            .onScrollGeometryChange(for: CGFloat.self) { $0.contentSize.height } action: { _, _ in
                if stick { scroller.scrollTo("bottom", anchor: .bottom) }
            }
            .onChange(of: rows.count) {
                if stick { withAnimation(.snappy) { scroller.scrollTo("bottom", anchor: .bottom) } }
            }
        }
        // Nothing else re-renders the page while it sits idle, so the moment
        // the newest tool row goes stale has to be waited for on purpose.
        .task(id: freshTool ? newest : nil) {
            guard freshTool, case let .event(e)? = rows.last else { return }
            let left = Self.liveMs - (diary.nowMs - e.t_ms)
            try? await Task.sleep(for: .milliseconds(max(0, left)))
            tick += 1
        }
    }
}

/// open breathes, connecting pings out, offline is the only one that holds
/// still.
struct ConnectionBadge: View {
    @Environment(Diary.self) private var diary

    var body: some View {
        let (color, text): (Color, String) = switch diary.conn {
        case .open: (.live, "session \(diary.session.map(String.init) ?? "-")")
        case .connecting: (.orange, "connecting")
        case .closed: (.red, "offline")
        }
        HStack(spacing: 6) {
            Circle().fill(color).frame(width: 7, height: 7)
                .phaseAnimator(diary.conn == .closed ? [1.0] : [1.0, 0.4]) { dot, fade in
                    dot.opacity(fade)
                } animation: { _ in .easeInOut(duration: diary.conn == .open ? 1.6 : 0.6) }
            Text(text).font(.caption.monospacedDigit()).contentTransition(.opacity)
            if diary.listening {
                Image(systemName: "waveform").font(.caption2).foregroundStyle(Color.live)
                    .help("The microphone is available")
                    .accessibilityLabel("microphone available")
            }
        }
        .padding(.horizontal, 8)
        .fixedSize()
    }
}

/// The book, made into the switch for the half it draws. Starting asks
/// nothing; stopping does, because the loop may be halfway through a word.
/// Nothing is optimistic: the cover swings when the server says so.
struct DiaryButton: View {
    @Environment(Diary.self) private var diary
    @State private var asking = false

    var body: some View {
        let presence = diary.diary
        let offline = diary.conn != .open
        Button {
            if presence.present { asking = true } else { diary.runDiary(true) }
        } label: {
            if presence.busy {
                ProgressView().controlSize(.small)
            } else {
                Image(systemName: presence.present ? "book" : "book.closed")
                    .contentTransition(.symbolEffect(.replace))
            }
        }
        .disabled(offline || presence.busy)
        .help(offline ? "Not connected, so there is nothing to ask."
              : presence.busy ? "Working on it."
              : presence.present ? "The diary is running and will answer a send. Press to stop it."
              : "The diary is not running. Press to start it.")
        .accessibilityLabel(presence.present ? "Stop the diary" : "Start the diary")
        .confirmationDialog("Stop the diary?", isPresented: $asking, titleVisibility: .visible) {
            Button("Stop it", role: .destructive) { diary.runDiary(false) }
            Button("Leave it running", role: .cancel) {}
        } message: {
            Text("The half that owns the pen goes down: the link to the tablet closes, anything it was drawing stops where it is, and nothing will answer a send until it is started again. "
                 + (presence.manager == "systemd"
                    ? "It is a service here, so it stays down until it is asked back."
                    : "It is started again from here, or with riddle diary start.")
                 + " What is written stays written.")
        }
    }
}

/// Start again: the ink off the page, the conversation dropped, the
/// timeline deleted. It asks first, because only one of those three can be
/// undone and it is not the ink.
struct EraseButton: View {
    @Environment(Diary.self) private var diary
    @State private var asking = false

    var body: some View {
        let ready = diary.conn == .open && diary.diary.serving
        Button { asking = true } label: { Image(systemName: "eraser") }
            .disabled(!ready)
            .help(ready ? "Erase this conversation"
                  : diary.diary.present ? "The diary is waiting for the tablet, so nothing can rub the page out yet."
                  : "The diary is not running, so nothing can rub the page out.")
            .accessibilityLabel("Erase this conversation")
            .confirmationDialog("Erase this conversation?", isPresented: $asking, titleVisibility: .visible) {
                Button("Erase", role: .destructive) { diary.clear() }
                Button("Keep it", role: .cancel) {}
            } message: {
                Text("The diary rubs its own ink off the page, starts a new conversation and deletes this session from the timeline, along with the captures and recordings it kept. What it wrote to memory survives. The ink cannot be brought back.")
            }
    }
}

#if os(iOS)
/// The gear on a phone: the switch, the microphone and the server, which on
/// the Mac sit under the composer and in Settings.
private struct PhoneMenu: View {
    let server: () -> Void
    @Environment(Diary.self) private var diary
    @Environment(Microphone.self) private var mic

    var body: some View {
        @Bindable var mic = mic
        Menu {
            Toggle(isOn: Binding(get: { diary.vanish }, set: { diary.setVanish($0) })) {
                Label("Vanish and answer", systemImage: "wand.and.sparkles")
            }
            .disabled(diary.conn != .open)
            if diary.listening {
                Picker(selection: $mic.chosen) {
                    Text("System default").tag(String?.none)
                    ForEach(mic.inputs) { input in Text(input.name).tag(Optional(input.id)) }
                } label: {
                    Label("Microphone", systemImage: "mic")
                    Text(mic.inputs.first { $0.id == mic.chosen }?.name ?? "System default")
                }
                .pickerStyle(.menu)
                .disabled(mic.state != .idle)
            }
            Divider()
            Button(action: server) { Label("Server…", systemImage: "server.rack") }
        } label: {
            Image(systemName: "gearshape")
        }
        .accessibilityLabel("Settings")
        .onAppear { mic.refresh() }
    }
}
#endif
