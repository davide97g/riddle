import Foundation
import Observation

/// The tablet's screen, for as long as somebody is looking at it.
///
/// Opening /ws/live is what asks for the feed and closing it is what ends
/// it, so there is no start or stop message. An open feed is somebody
/// watching as far as the diary knows -- it keeps its hands off the page --
/// so the Live view hangs up whenever it is not on screen: another tab, the
/// app in the background, the window closed.
@Observable
final class LiveFeed {
    enum State: Equatable { case off, dialing, on, lost, refused }

    private static let maxBackoff = 5.0

    /// the newest frame as the server sent it, a png
    private(set) var frame: Data?
    private(set) var state: State = .off
    private(set) var message: String?
    /// When the frame last changed. Only changed frames are sent, so this is
    /// when somebody last moved the pen, not when the server last looked.
    private(set) var changedAt: Date?

    private var task: URLSessionWebSocketTask?
    private var generation = 0
    private var attempt = 0
    private var retry: Task<Void, Never>?
    private var server: Server?

    func open(_ server: Server) {
        guard task == nil else { return }
        self.server = server
        attempt = 0
        state = .dialing
        message = nil
        connect()
    }

    /// Hung up on purpose. The last frame stays, faded: it is what the page
    /// was when you looked away, and it is replaced when the feed is back.
    func close() {
        generation += 1
        retry?.cancel()
        task?.cancel(with: .normalClosure, reason: nil)
        task = nil
        server = nil
        if state != .refused { state = .off }
        message = nil
    }

    private func connect() {
        guard let server else { return }
        generation += 1
        let mine = generation
        let sock = API.session.webSocketTask(with: server.socket("/ws/live"))
        sock.maximumMessageSize = 32 << 20
        task = sock
        sock.resume()

        Task { [weak self] in
            while true {
                let got: URLSessionWebSocketTask.Message
                do { got = try await sock.receive() } catch {
                    self?.dropped(sock, mine)
                    return
                }
                guard let self, self.generation == mine else { return }
                self.attempt = 0
                switch got {
                case let .data(png):
                    self.frame = png
                    self.changedAt = Date()
                case let .string(text):
                    guard let said = try? JSONDecoder().decode(LiveMessage.self, from: Data(text.utf8)) else { break }
                    switch said.type {
                    case "live":
                        self.state = switch said.state {
                        case "on": .on
                        case "lost": .lost
                        default: .dialing
                        }
                        self.message = said.message
                    default:
                        break
                    }
                @unknown default:
                    break
                }
            }
        }
    }

    private func dropped(_ sock: URLSessionWebSocketTask, _ mine: Int) {
        guard generation == mine else { return }
        task = nil
        // 1008 is the gate: RIDDLE_ALLOW_SNAP is off, and asking again every
        // few seconds will not turn it on.
        if sock.closeCode == .policyViolation {
            state = .refused
            message = sock.closeReason.map { String(decoding: $0, as: UTF8.self) }
            return
        }
        state = .lost
        message = "lost the server"
        let wait = min(Self.maxBackoff, 0.25 * pow(2, Double(attempt)))
        attempt += 1
        retry = Task { [weak self] in
            try? await Task.sleep(for: .seconds(wait * Double.random(in: 0.7...1.3)))
            guard !Task.isCancelled, let self, self.generation == mine else { return }
            self.connect()
        }
    }
}
