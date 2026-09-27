import SwiftUI
import UniformTypeIdentifiers

/// Live: the page on the tablet as it is right now, and the snapshots kept
/// of it. There is no control here that reaches the pen.
///
/// `showing` is whether this page is actually on screen. The feed is open
/// only while it is, because an open feed is somebody watching as far as
/// the diary knows, and it keeps its hands off the page for as long as one
/// is.
struct LiveView: View {
    let showing: Bool
    @Environment(Connection.self) private var connection
    @Environment(Diary.self) private var diary
    @Environment(Snapshots.self) private var snapshots
    @Environment(Toasts.self) private var toasts
    @Environment(\.horizontalSizeClass) private var width
    @State private var feed = LiveFeed()
    @State private var open: Snapshot?
    @AppStorage("riddle.look") private var look: Look = .paper

    var body: some View {
        let wide = width != .compact
        Group {
            if wide {
                HStack(spacing: 0) {
                    screen
                    Divider()
                    Shelf(open: $open, look: look, wide: true).frame(width: 240)
                }
            } else {
                VStack(spacing: 0) {
                    screen
                    if !snapshots.list.isEmpty {
                        Divider()
                        Shelf(open: $open, look: look, wide: false)
                    }
                }
            }
        }
        .toolbar {
            if width != .compact {
                ToolbarItem(placement: .principal) { Wordmark().frame(height: 18) }
            }
            ToolbarItemGroup(placement: .primaryAction) {
                Button {
                    look = look == .paper ? .ink : .paper
                } label: {
                    Label(look == .paper ? "Paper" : "Ink", systemImage: "circle.lefthalf.filled")
                }
                .help(look == .paper
                      ? "Showing the page as it is. Press to show only the ink, on the theme."
                      : "Showing only the ink, on the theme. Press to show the page as it is.")
                Button { understandNow() } label: { Label("Understand", systemImage: "sparkles") }
                    .disabled(feed.frame == nil)
                    .help("Snapshot this page and ask what is on it")
                Button { snap() } label: { Label("Snapshot", systemImage: "camera") }
                    .disabled(feed.frame == nil)
                    .help("Copy this page and keep it on the shelf")
                    .keyboardShortcut("s", modifiers: .command)
                SendToTabletButton()
            }
        }
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .sheet(item: $open) { snap in
            SnapshotDetail(snapID: snap.id, look: look)
        }
        .onChange(of: showing, initial: true) { _, on in sync(on) }
        .onChange(of: connection.server) { _, _ in
            feed.close()
            sync(showing)
        }
        .onDisappear { feed.close() }
    }

    private var screen: some View {
        VStack(spacing: 10) {
            FeedStatus(feed: feed, allowed: diary.live || diary.conn != .open)
            if let png = feed.frame, let image = PlatformImage(data: png) {
                Image(platform: image)
                    .resizable()
                    .scaledToFit()
                    .look(look)
                    .background(look == .paper ? Color.white : Color.clear)
                    .clipShape(.rect(cornerRadius: 4))
                    .overlay { RoundedRectangle(cornerRadius: 4).strokeBorder(Color.primary.opacity(0.12)) }
                    // A stale frame is still the page, but it must not pass
                    // for a live one while the link is down.
                    .opacity(feed.state == .on ? 1 : 0.5)
                    .animation(.easeOut(duration: 0.3), value: feed.state)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .accessibilityLabel("The page open on the tablet, right now")
            } else {
                ContentUnavailableView {
                    Label(feed.state == .refused ? "Not allowed" : "Waiting for the page",
                          systemImage: feed.state == .refused ? "eye.slash" : "rectangle.portrait")
                } description: {
                    Text(feed.state == .refused
                         ? "The server may not read the screen: set RIDDLE_ALLOW_SNAP=1."
                         : "The first frame arrives once the tablet answers.")
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .padding(16)
    }

    private func sync(_ on: Bool) {
        if on, let server = connection.server { feed.open(server) } else { feed.close() }
    }

    /// Onto the clipboard and onto the shelf, both at once, because the one
    /// you did not pick is the one you wanted.
    private func snap() {
        guard let png = feed.frame else { return }
        Clipboard.png(png)
        if snapshots.take(png) != nil {
            toasts.success("Snapshot copied", "Kept on the shelf too.")
        } else {
            toasts.failure("Could not keep it")
        }
    }

    /// A snapshot first, so the reading has somewhere to live, and its
    /// preview opens so the answer arrives where you are looking.
    private func understandNow() {
        guard let png = feed.frame, let server = connection.server, let snap = snapshots.take(png) else { return }
        open = snap
        Task { await snapshots.understand(snap, server: server) }
    }
}

private struct FeedStatus: View {
    let feed: LiveFeed
    let allowed: Bool

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            HStack(spacing: 8) {
                switch feed.state {
                case .on: Circle().fill(Color.live).frame(width: 7, height: 7)
                case .refused: Circle().fill(.red).frame(width: 7, height: 7)
                default: Image(systemName: "waveform").font(.caption).symbolEffect(.variableColor.iterative, options: .repeating)
                }
                Text(said(context.date)).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                Spacer()
            }
        }
    }

    private func said(_ now: Date) -> String {
        let why = feed.message.map { ": \($0)" } ?? ""
        switch feed.state {
        case .on:
            guard let at = feed.changedAt else { return "live" }
            return "live · last change \(ago(now.timeIntervalSince(at)))"
        case .lost: return "lost the tablet\(why) · redialling"
        case .refused: return "the server will not read the screen\(why)"
        case .off: return allowed ? "paused while this page is not showing" : "the server may not read the screen"
        case .dialing: return "dialing the tablet"
        }
    }

    private func ago(_ s: TimeInterval) -> String {
        let s = Int(s.rounded())
        if s < 2 { return "just now" }
        if s < 60 { return "\(s)s ago" }
        let m = s / 60
        return m < 60 ? "\(m) min ago" : "\(m / 60) h ago"
    }
}

/// The last ten snapshots, newest first. A column beside the page where
/// there is room, a strip under it on a phone.
private struct Shelf: View {
    @Binding var open: Snapshot?
    let look: Look
    let wide: Bool
    @Environment(Snapshots.self) private var snapshots

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 4) {
                Text("SNAPSHOTS").font(.caption2.weight(.medium)).tracking(0.6)
                if !snapshots.list.isEmpty {
                    Text("· \(snapshots.list.count)/\(Snapshots.max)").font(.caption2.monospacedDigit())
                }
            }
            .foregroundStyle(.secondary)
            if snapshots.list.isEmpty {
                Text("Take one and it lands here, and on your clipboard. Understand one to have it read.")
                    .font(.caption).foregroundStyle(.secondary)
            } else if wide {
                ScrollView {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                        ForEach(snapshots.list) { snap in Thumb(snap: snap, look: look) { open = snap } }
                    }
                }
            } else {
                ScrollView(.horizontal) {
                    LazyHStack(spacing: 10) {
                        ForEach(snapshots.list) { snap in
                            Thumb(snap: snap, look: look) { open = snap }.frame(width: 72)
                        }
                    }
                }
                .frame(height: 124)
            }
        }
        .padding(12)
        .frame(maxHeight: wide ? .infinity : nil, alignment: .top)
    }
}

private struct Thumb: View {
    let snap: Snapshot
    let look: Look
    let tap: () -> Void
    @Environment(Snapshots.self) private var snapshots

    var body: some View {
        Button(action: tap) {
            VStack(alignment: .leading, spacing: 4) {
                Group {
                    if let data = snapshots.png(snap), let image = PlatformImage(data: data) {
                        Image(platform: image).resizable().scaledToFit().look(look)
                    } else {
                        Color.clear
                    }
                }
                .aspectRatio(1404.0 / 1872.0, contentMode: .fit)
                .background(look == .paper ? Color.white : Color.clear)
                .clipShape(.rect(cornerRadius: 3))
                .overlay { RoundedRectangle(cornerRadius: 3).strokeBorder(Color.primary.opacity(0.12)) }
                .overlay(alignment: .topTrailing) {
                    if snapshots.reading[snap.id] == .reading {
                        ProgressView().controlSize(.mini).padding(4)
                    } else if snap.understood != nil {
                        Image(systemName: "sparkles").font(.caption2).padding(4)
                            .background(.regularMaterial, in: .circle).padding(3)
                    }
                }
                Text(snap.at.clock).font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Open the snapshot from \(snap.at.formatted())")
    }
}

/// One kept frame, full size beside what the model made of it. What is
/// copied or saved is the frame as the tablet sent it -- white paper, black
/// ink -- whatever the look did to the preview.
private struct SnapshotDetail: View {
    let snapID: UUID
    let look: Look
    @Environment(Snapshots.self) private var snapshots
    @Environment(Connection.self) private var connection
    @Environment(Toasts.self) private var toasts
    @Environment(\.dismiss) private var dismiss
    @State private var saving = false

    var body: some View {
        NavigationStack {
            if let snap = snapshots.list.first(where: { $0.id == snapID }) {
                ScrollView {
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .top, spacing: 20) {
                            picture(snap).frame(maxWidth: 420)
                            Understood(snap: snap, understand: { understand(snap) }).frame(minWidth: 280)
                        }
                        VStack(alignment: .leading, spacing: 20) {
                            picture(snap).frame(maxHeight: 420)
                            Understood(snap: snap, understand: { understand(snap) })
                        }
                    }
                    .padding(20)
                }
                .navigationTitle(snap.at.formatted(date: .abbreviated, time: .standard))
                #if os(iOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
                    ToolbarItemGroup(placement: .primaryAction) {
                        Button { copy(snap) } label: { Label("Copy", systemImage: "doc.on.doc") }
                        ShareLink(item: snapshots.file(snap)) { Label("Share", systemImage: "square.and.arrow.up") }
                        #if os(macOS)
                        Button { saving = true } label: { Label("Save", systemImage: "arrow.down.to.line") }
                        #endif
                        Button { understand(snap) } label: {
                            Label(snap.understood == nil ? "Understand" : "Understand again", systemImage: "sparkles")
                        }
                        .disabled(snapshots.reading[snap.id] == .reading)
                        Button(role: .destructive) {
                            snapshots.remove(snap)
                            dismiss()
                        } label: { Label("Delete", systemImage: "trash") }
                    }
                }
                .fileExporter(isPresented: $saving, document: PNGFile(data: snapshots.png(snap) ?? Data()),
                              contentType: .png, defaultFilename: snap.fileName) { result in
                    if case let .failure(error) = result { toasts.failure("Could not save it", error.localizedDescription) }
                }
            } else {
                ContentUnavailableView("That snapshot is gone", systemImage: "photo")
            }
        }
        #if os(macOS)
        .frame(minWidth: 720, minHeight: 560)
        #endif
    }

    private func picture(_ snap: Snapshot) -> some View {
        Group {
            if let data = snapshots.png(snap), let image = PlatformImage(data: data) {
                Image(platform: image).resizable().scaledToFit().look(look)
                    .background(look == .paper ? Color.white : Color.clear)
                    .clipShape(.rect(cornerRadius: 4))
                    .overlay { RoundedRectangle(cornerRadius: 4).strokeBorder(Color.primary.opacity(0.12)) }
            }
        }
    }

    private func copy(_ snap: Snapshot) {
        guard let data = snapshots.png(snap) else { return }
        Clipboard.png(data)
        toasts.success("Copied to the clipboard")
    }

    private func understand(_ snap: Snapshot) {
        guard let server = connection.server else { return }
        Task { await snapshots.understand(snap, server: server) }
    }
}

/// What the model made of a page, laid out rather than printed. An old
/// reading stays, dimmed, while a new one is fetched: the page it describes
/// has not changed.
private struct Understood: View {
    let snap: Snapshot
    let understand: () -> Void
    @Environment(Snapshots.self) private var snapshots
    @Environment(Toasts.self) private var toasts

    var body: some View {
        let status = snapshots.reading[snap.id]
        VStack(alignment: .leading, spacing: 16) {
            if snap.understood == nil, status == nil {
                Text("Ask what is on this page: the writing as text, and what the drawing means. The snapshot is sent to OpenAI to be read.")
                    .font(.callout).foregroundStyle(.secondary)
                Button(action: understand) { Label("Understand", systemImage: "sparkles") }
                    .buttonStyle(.borderedProminent)
            }
            if status == .reading {
                StatusLine(symbol: "ellipsis") { Text("reading the page") }
            }
            if case let .failed(why)? = status {
                Text("Could not read it: \(why)").font(.callout).foregroundStyle(.red)
                Button("Try again", action: understand).buttonStyle(.bordered)
            }
            if let read = snap.understood {
                VStack(alignment: .leading, spacing: 14) {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 8) {
                            Text(read.title).font(.headline)
                            Text(read.kind).font(.caption)
                                .padding(.horizontal, 7).padding(.vertical, 2)
                                .overlay { Capsule().strokeBorder(Color.primary.opacity(0.2)) }
                        }
                        Text("read by \(read.model) in \(String(format: "%.1f", Double(read.took_ms) / 1000))s")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Text(read.summary).font(.callout).textSelection(.enabled)
                    if !read.points.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            ForEach(Array(read.points.enumerated()), id: \.offset) { _, point in
                                HStack(alignment: .firstTextBaseline, spacing: 8) {
                                    Text("•")
                                    Text(point).textSelection(.enabled)
                                }
                                .font(.callout)
                            }
                        }
                    }
                    if !read.transcript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            HStack {
                                Text("TRANSCRIPT").font(.caption2.weight(.medium)).tracking(0.6).foregroundStyle(.secondary)
                                Spacer()
                                Button {
                                    Clipboard.text(read.transcript)
                                    toasts.success("Transcript copied")
                                } label: { Image(systemName: "doc.on.doc") }
                                .buttonStyle(.borderless)
                                .accessibilityLabel("Copy the transcript")
                            }
                            Text(read.transcript)
                                .font(.caption.monospaced())
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(10)
                                .background(.background.secondary, in: .rect(cornerRadius: 8))
                        }
                    }
                }
                .opacity(status == .reading ? 0.4 : 1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct PNGFile: FileDocument {
    static let readableContentTypes: [UTType] = [.png]
    let data: Data

    init(data: Data) { self.data = data }

    init(configuration: ReadConfiguration) throws {
        data = configuration.file.regularFileContents ?? Data()
    }

    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        FileWrapper(regularFileWithContents: data)
    }
}
