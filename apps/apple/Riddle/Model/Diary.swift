import Foundation
import Observation

/// A row on screen: something the server told us, or something we have said
/// but not yet seen come back.
enum Row: Identifiable, Equatable {
    case event(DiaryEvent)
    case pending(Pending)

    struct Pending: Equatable {
        let id: String
        let tMs: Int
        let text: String
        var failed = false
        /// set once the server has acknowledged the send
        var intent: Int?
    }

    var id: String {
        switch self {
        case let .event(e): "e\(e.id)"
        case let .pending(p): p.id
        }
    }

    var tMs: Int {
        switch self {
        case let .event(e): e.t_ms
        case let .pending(p): p.tMs
        }
    }
}

/// The main page's state and everything that changes it: the same reducer
/// as apps/web/src/state/reducer.ts, and the same actions as its provider.
@Observable
final class Diary {
    typealias Conn = EventsSocket.Conn

    /// highest event id applied, and what `hello` resumes from
    private(set) var seq = 0
    private(set) var rows: [String: Row] = [:]
    /// row ids, kept sorted by t_ms
    private(set) var order: [String] = []
    private(set) var session: Int?
    private(set) var startedMs: Int?
    /// The server's own t_ms when it greeted us, and a clock that cannot
    /// step at that moment. A phone whose clock is a few seconds off the
    /// server's would otherwise drop its own rows into the wrong place in a
    /// list sorted by t_ms, so elapsed time is measured rather than assumed.
    private var serverNowMs: Int?
    private var greetedAt: TimeInterval?
    private(set) var listening = false
    /// whether the server will stream the tablet's screen
    private(set) var live = false
    /// whether the diary fades the ink and answers after a pause
    private(set) var vanish = true
    /// whether the server had a value for it, or only the default
    private(set) var vanishKnown = false
    /// somebody has the page open on Live, so the diary keeps its hands off
    private(set) var watched: Watcher?
    /// whether the half that owns the pen is running
    private(set) var diary = DiaryPresence.unknown
    private(set) var conn: Conn = .connecting
    var draft = ""
    /// somebody is speaking right now
    private(set) var hearing = false
    /// clips the model is still working through
    private(set) var reading: [String] = []
    /// the newest failure the server reported, for a toast
    var failure: String?

    private let socket = EventsSocket()
    private var pendingSend: String?
    private static let vanishKey = "riddle.vanish"

    init() {
        socket.since = { [weak self] in self?.seq ?? 0 }
        socket.onConn = { [weak self] conn in self?.conn = conn }
        socket.onMessage = { [weak self] message in self?.apply(message) }
    }

    func start(_ server: Server) { socket.start(server) }

    func stop() {
        socket.stop()
        seq = 0
        rows = [:]
        order = []
        conn = .closed
    }

    func wake() { socket.wake() }

    var inOrder: [Row] { order.compactMap { rows[$0] } }

    /// The session clock, as this app best knows it: what the server said
    /// when it greeted us, plus how long ago that was by a clock that cannot
    /// step.
    var nowMs: Int {
        guard let serverNowMs, let greetedAt else {
            guard let startedMs else { return 0 }
            return Int(Date().timeIntervalSince1970 * 1000) - startedMs
        }
        return serverNowMs + Int((ProcessInfo.processInfo.systemUptime - greetedAt) * 1000)
    }

    // MARK: actions

    func note(_ text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        // Shown at once; the server's echo replaces this row in place.
        let id = UUID().uuidString
        place(.pending(.init(id: id, tMs: nowMs, text: trimmed)))
        if !socket.send(.note(text: trimmed)) { fail(id) }
    }

    func send() {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        let id = UUID().uuidString
        // One optimistic row for the whole send, tagged with the intent id
        // when the server acknowledges it, so the reply replaces it in place.
        place(.pending(.init(id: id, tMs: nowMs, text: text.isEmpty ? "asking the diary" : text)))
        pendingSend = id
        // `at_ms` is when the button was pressed, not when the loop notices,
        // so the tail of what you were still saying belongs to this turn.
        if !socket.send(.send(atMs: nowMs, draft: text)) { fail(id) }
        draft = ""
    }

    func clear() {
        // The rows go now; the ink takes as long as the eraser takes.
        rows = [:]
        order = []
        socket.send(.clear)
    }

    /// Nothing optimistic: the server says `busy` straight back and `diary`
    /// again when it is done. A book that swung open before the loop was up
    /// would be the app claiming a pen it has not got.
    func runDiary(_ up: Bool) {
        socket.send(up ? .diaryStart : .diaryStop)
    }

    /// Optimistic, unlike the diary's own switch: this is a setting, not a
    /// process, and the server's echo says the same a moment later.
    func setVanish(_ on: Bool) {
        UserDefaults.standard.set(on, forKey: Self.vanishKey)
        vanish = on
        vanishKnown = true
        socket.send(.vanish(on: on))
    }

    // MARK: the reducer

    private func apply(_ message: ServerMessage) {
        switch message {
        case let .hello(hello):
            conn = .open
            session = hello.session
            startedMs = hello.started_ms
            serverNowMs = hello.now_ms
            greetedAt = ProcessInfo.processInfo.systemUptime
            listening = hello.listening
            live = hello.live ?? false
            watched = hello.watched
            diary = hello.diary ?? diary
            if let on = hello.vanish {
                vanish = on
                vanishKnown = true
                UserDefaults.standard.set(on, forKey: Self.vanishKey)
            } else {
                // A server that has never been told takes this app's word.
                vanishKnown = false
                if let mine = UserDefaults.standard.object(forKey: Self.vanishKey) as? Bool {
                    setVanish(mine)
                }
            }
        case let .intentOK(id, _):
            if let pending = pendingSend, case var .pending(row)? = rows[pending] {
                row.intent = id
                rows[pending] = .pending(row)
            }
            pendingSend = nil
        case let .diary(presence):
            diary = presence
        case let .vanish(on):
            vanish = on
            vanishKnown = true
            UserDefaults.standard.set(on, forKey: Self.vanishKey)
        case let .watched(by):
            watched = by
        case let .hearing(on):
            hearing = on
        case let .pending(clip, on):
            reading = on ? reading + [clip] : reading.filter { $0 != clip }
        case let .event(event):
            seq = max(seq, event.id)
            // The rows behind this one were deleted from the store, so the
            // app drops them rather than showing a past nothing else can see.
            if event.kind == .tool, event.meta["doing"]?.string == "cleared" {
                rows = [:]
                order = []
                return
            }
            settle(event)
        case let .error(text):
            failure = text
        case .pong, .unknown:
            break
        }
    }

    private func fail(_ id: String) {
        guard case var .pending(row)? = rows[id] else { return }
        row.failed = true
        rows[id] = .pending(row)
    }

    /// Insert keeping `order` sorted by when the thing happened. Not by id:
    /// transcription lags by seconds, so what you said arrives after the
    /// strokes you wrote while waiting for it.
    private func place(_ row: Row) {
        let existed = rows[row.id] != nil
        rows[row.id] = row
        if existed { return }
        var at = order.count
        while at > 0, (rows[order[at - 1]]?.tMs ?? 0) > row.tMs { at -= 1 }
        order.insert(row.id, at: at)
    }

    /// A note or send we made optimistically comes back as a real row, and
    /// replaces it in place so nothing jumps. By intent id where there is
    /// one: a send and the reply it causes share no text at all.
    private func settle(_ event: DiaryEvent) {
        let intent = event.meta["intent"]?.int
        let pending = order.first { id in
            guard case let .pending(row)? = rows[id] else { return false }
            if let intent, row.intent == intent { return true }
            return event.kind == .note && row.text == event.text
        }
        if let pending {
            rows[pending] = nil
            order.removeAll { $0 == pending }
        }
        place(.event(event))
    }
}
