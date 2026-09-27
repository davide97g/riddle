import Foundation

/// /ws/events: the feed and the send path both.
///
/// The socket is the source of truth, not a cache to invalidate. Every
/// persisted event carries a monotonic id, so reconnecting is
/// `hello {since}` and the diary's dedupe absorbs the overlap. There is no
/// other resync path and there does not need to be one.
final class EventsSocket {
    enum Conn { case connecting, open, closed }

    private static let maxBackoff = 5.0
    private static let heartbeat = 15.0
    private static let pongDeadline = 10.0

    var onMessage: (ServerMessage) -> Void = { _ in }
    var onConn: (Conn) -> Void = { _ in }
    /// the highest event id applied, read at every dial
    var since: () -> Int = { 0 }

    private var server: Server?
    private var task: URLSessionWebSocketTask?
    /// Bumped on every dial and every hang-up, so a callback from a socket
    /// that has since been replaced does nothing.
    private var generation = 0
    private var attempt = 0
    private var retry: Task<Void, Never>?
    private var beat: Task<Void, Never>?
    private var lastPong = Date()
    private(set) var isOpen = false

    func start(_ server: Server) {
        if self.server == server, task != nil { return }
        stop()
        self.server = server
        attempt = 0
        connect()
    }

    func stop() {
        generation += 1
        server = nil
        retry?.cancel()
        beat?.cancel()
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        isOpen = false
    }

    /// Back from the background, or the network came back: redial now
    /// rather than waiting out the backoff.
    func wake() {
        guard server != nil, !isOpen else { return }
        retry?.cancel()
        attempt = 0
        connect()
    }

    /// Dropped on purpose while closed. A turn queued now and delivered in
    /// four minutes would draw on whatever page is open then.
    @discardableResult
    func send(_ message: ClientMessage) -> Bool {
        guard isOpen, let task else { return false }
        task.send(.string(message.json)) { _ in }
        return true
    }

    private func connect() {
        guard let server else { return }
        generation += 1
        let mine = generation
        task?.cancel(with: .goingAway, reason: nil)
        beat?.cancel()
        isOpen = false
        onConn(.connecting)

        let sock = API.session.webSocketTask(with: server.socket("/ws/events"))
        sock.maximumMessageSize = 16 << 20
        task = sock
        sock.resume()
        lastPong = Date()
        sock.send(.string(ClientMessage.hello(since: since(), limit: 500).json)) { _ in }

        Task { [weak self] in
            while true {
                let got: URLSessionWebSocketTask.Message
                do { got = try await sock.receive() } catch {
                    self?.closed(mine)
                    return
                }
                guard let self, self.generation == mine else { return }
                let data: Data = switch got {
                case let .string(text): Data(text.utf8)
                case let .data(data): data
                @unknown default: Data()
                }
                guard let message = try? ServerMessage.decode(data) else { continue }
                self.lastPong = Date()
                if case .hello = message {
                    self.isOpen = true
                    self.attempt = 0
                    self.startBeat(sock, mine)
                }
                if case .pong = message { continue }
                self.onMessage(message)
            }
        }
    }

    private func startBeat(_ sock: URLSessionWebSocketTask, _ mine: Int) {
        beat?.cancel()
        beat = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(Self.heartbeat))
                guard let self, self.generation == mine, !Task.isCancelled else { return }
                if Date().timeIntervalSince(self.lastPong) > Self.heartbeat + Self.pongDeadline {
                    sock.cancel(with: .goingAway, reason: nil)
                    return
                }
                let now = Int(Date().timeIntervalSince1970 * 1000)
                sock.send(.string(ClientMessage.ping(t: now).json)) { _ in }
            }
        }
    }

    private func closed(_ mine: Int) {
        guard generation == mine, server != nil else { return }
        beat?.cancel()
        isOpen = false
        task = nil
        onConn(.closed)
        // Jittered backoff, so a server restart does not meet a thundering
        // herd of one.
        let wait = min(Self.maxBackoff, 0.25 * pow(2, Double(attempt)))
        attempt += 1
        retry = Task { [weak self] in
            try? await Task.sleep(for: .seconds(wait * Double.random(in: 0.7...1.3)))
            guard !Task.isCancelled, let self, self.generation == mine else { return }
            self.connect()
        }
    }
}
