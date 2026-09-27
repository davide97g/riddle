import SwiftUI

/// Who a row belongs to decides which edge it sits against: what you said
/// or wrote hangs off the right, what the diary answered off the left, the
/// way any chat reads. `full` is for rows that belong to neither.
private enum Side { case mine, theirs, full }

private struct Card<Content: View>: View {
    let label: String
    let at: Date?
    var side: Side = .full
    var tint: Color? = nil
    var faded = false
    @ViewBuilder let content: Content

    var body: some View {
        let card = VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(label.uppercased())
                    .font(.caption2.weight(.medium))
                    .tracking(0.6)
                    .foregroundStyle(tint ?? .secondary)
                Spacer(minLength: 12)
                if let at {
                    Text(at.clock).font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
                }
            }
            content
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(side == .theirs ? AnyShapeStyle(.quaternary.opacity(0.6)) : AnyShapeStyle(.background.secondary),
                    in: .rect(cornerRadius: 12))
        .overlay {
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(tint?.opacity(0.4) ?? Color.primary.opacity(side == .theirs ? 0.15 : 0.08))
        }
        .opacity(faded ? 0.7 : 1)

        switch side {
        case .full: card
        case .mine: HStack { Spacer(minLength: 48); card }
        case .theirs: HStack { card; Spacer(minLength: 48) }
        }
    }
}

/// `*asterisks*` mean the same here as they do on the page: the hand leans
/// on them, so the screen and the tablet agree about what the diary stressed.
func emphasised(_ text: String) -> Text {
    var out = AttributedString()
    var rest = Substring(text)
    while let open = rest.firstIndex(of: "*") {
        let after = rest.index(after: open)
        guard let close = rest[after...].firstIndex(of: "*"), close > after else { break }
        out += AttributedString(rest[..<open])
        var leaned = AttributedString(rest[after..<close])
        leaned.inlinePresentationIntent = .stronglyEmphasized
        out += leaned
        rest = rest[rest.index(after: close)...]
    }
    out += AttributedString(rest)
    return Text(out)
}

struct EventRow: View {
    let event: DiaryEvent
    /// the newest row: a reply writes itself on, a tool row may move
    var newest = false
    var live = false

    var body: some View {
        switch event.kind {
        case .strokes: StrokesRow(event: event)
        case .shot: ShotRow(event: event)
        case .speech:
            Card(label: "said", at: event.wall, side: .mine) { plain(event.text) }
        case .note:
            // A note the diary wrote to itself, rather than one you typed.
            Card(label: event.meta["remember"]?.bool == true ? "kept" : "typed", at: event.wall, side: .mine) {
                plain(event.text)
            }
        case .reply:
            Card(label: "the diary", at: event.wall, side: .theirs) {
                emphasised(event.text ?? "")
                    .font(.body)
                    .lineSpacing(3)
                    .textSelection(.enabled)
                    .transition(.opacity)
            }
        case .tool:
            ToolRow(doing: event.meta["doing"]?.string ?? event.text ?? "thinking", live: live)
        case .error:
            Card(label: "went wrong", at: event.wall, tint: .red) {
                Text(event.text ?? "").font(.callout).foregroundStyle(.red).textSelection(.enabled)
            }
        case nil:
            EmptyView()
        }
    }

    private func plain(_ text: String?) -> some View {
        Text(text ?? "").font(.body).lineSpacing(3).textSelection(.enabled)
    }
}

struct PendingRowView: View {
    let row: Row.Pending

    var body: some View {
        Card(label: row.failed ? "not delivered" : "sending", at: nil, side: .mine,
             tint: row.failed ? .red : nil, faded: !row.failed) {
            Text(row.text).font(.body)
            if !row.failed { ProgressView().progressViewStyle(.linear).frame(width: 96).tint(.secondary) }
        }
    }
}

/// The page is the whole point of a strokes row, so it is shown as large as
/// the card allows and opens full size on a tap.
private struct StrokesRow: View {
    let event: DiaryEvent

    var body: some View {
        let strokes = event.meta["strokes"]?.int ?? 0
        Card(label: "written", at: event.wall, side: .mine) {
            Text("\(strokes) stroke\(strokes == 1 ? "" : "s")"
                 + (event.dur_ms > 0 ? " over \(String(format: "%.1f", Double(event.dur_ms) / 1000))s" : ""))
                .font(.callout)
                .foregroundStyle(.secondary)
            if let path = event.path {
                CaptureImage(path: path, alt: "what was written").frame(maxHeight: 320)
            }
        }
    }
}

/// The whole page, photographed before the eraser ran, and folded away.
/// Left open it would repeat your own handwriting down the timeline and
/// drown the conversation it exists to be context for.
private struct ShotRow: View {
    let event: DiaryEvent
    @State private var open = false

    var body: some View {
        if let path = event.path {
            VStack(alignment: .leading, spacing: 8) {
                Button {
                    withAnimation(.snappy) { open.toggle() }
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "chevron.right")
                            .font(.caption2.weight(.semibold))
                            .rotationEffect(.degrees(open ? 90 : 0))
                            .frame(width: 24)
                        Text("the whole page, photographed at \(event.wall.clock)")
                            .font(.caption)
                    }
                    .foregroundStyle(.secondary)
                    .contentShape(.rect)
                }
                .buttonStyle(.plain)
                if open { CaptureImage(path: path, alt: "the tablet's screen").frame(maxHeight: 320) }
            }
        }
    }
}

/// What the diary is doing, or was. Only the newest row is still happening,
/// so the motion belongs to the last row alone and only for a minute.
struct ToolRow: View {
    let doing: String
    let live: Bool

    var body: some View {
        StatusLine(symbol: symbol, moving: live) { Text("the diary is \(doing)") }
    }

    /// Matched on a stem rather than a list: the loop is free to invent a
    /// verb, and an unknown one should still look like work.
    private var symbol: String {
        let d = doing.lowercased()
        if ["eras", "rubb", "clear", "wip"].contains(where: d.contains) { return "eraser" }
        if ["writ", "draw", "ink", "sketch", "answer"].contains(where: d.contains) { return "pencil.and.scribble" }
        return "ellipsis"
    }
}

struct StatusLine<Label: View>: View {
    let symbol: String
    var moving = true
    @ViewBuilder let label: Label

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: symbol)
                .font(.caption)
                .frame(width: 24)
                .symbolEffect(.pulse, options: .repeating, isActive: moving)
            label.font(.caption)
        }
        .foregroundStyle(.secondary)
        .padding(.horizontal, 4)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// A png out of `var/captures`, fetched with the cookie. The capture is
/// opaque on purpose -- it is also what the model is shown -- so the paper
/// is dropped here instead, and what is left is the ink on the card.
struct CaptureImage: View {
    let path: String
    let alt: String
    @Environment(Connection.self) private var connection
    @State private var image: PlatformImage?
    @State private var missing = false
    @State private var zoomed = false

    var body: some View {
        Group {
            if missing {
                Text("that page is no longer on disk").font(.caption).foregroundStyle(.secondary)
            } else if let image {
                Button { zoomed = true } label: {
                    Image(platform: image)
                        .resizable()
                        .scaledToFit()
                        .look(.ink)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(alt)
                .sheet(isPresented: $zoomed) {
                    ZoomedImage(image: image, title: alt, look: .ink)
                }
            } else {
                Color.clear.frame(height: 120)
            }
        }
        .task(id: path) { await load() }
    }

    private func load() async {
        if let cached = CaptureCache.shared.object(forKey: path as NSString) {
            image = cached
            return
        }
        guard let server = connection.server else { return }
        do {
            let data = try await API.capture(server, path: path)
            guard let made = PlatformImage(data: data) else { missing = true; return }
            CaptureCache.shared.setObject(made, forKey: path as NSString)
            withAnimation(.easeOut(duration: 0.3)) { image = made }
        } catch {
            missing = true
        }
    }
}

enum CaptureCache {
    static let shared: NSCache<NSString, PlatformImage> = {
        let cache = NSCache<NSString, PlatformImage>()
        cache.countLimit = 80
        return cache
    }()
}

/// A picture opened full size, with nothing else in the way.
struct ZoomedImage: View {
    let image: PlatformImage
    let title: String
    let look: Look
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Image(platform: image)
                .resizable()
                .scaledToFit()
                .look(look)
                .padding()
                .navigationTitle(title)
                #if os(iOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
                }
        }
        #if os(macOS)
        .frame(minWidth: 520, minHeight: 640)
        #endif
    }
}
