// The wire, written out by hand, the same as apps/web/src/lib/protocol.ts.
// Both are mirrors of docs/protocols.md, and a change there is a change here
// in the same commit. `riddle check` reads this file for the event kinds and
// the messages the server sends.

import Foundation

/// Anything that can be on the timeline. `riddle check` holds this against
/// `KINDS` in riddle/store/db.py.
nonisolated enum EventKind: String, Codable, Sendable {
    case strokes
    case speech
    case shot
    case reply
    case note
    case tool
    case error
}

nonisolated struct DiaryEvent: Codable, Sendable, Identifiable, Equatable {
    let id: Int
    /// A kind this build does not know is kept as nil rather than failing the
    /// whole message: a newer server must not blank an older app's timeline.
    let kind: EventKind?
    /// ms since the session started. This is what the timeline sorts by.
    let t_ms: Int
    let dur_ms: Int
    /// unix epoch ms, for saying what time of day something happened
    let wall_ms: Int
    let turn: Int?
    let text: String?
    let path: String?
    let meta: [String: JSONValue]

    enum CodingKeys: String, CodingKey {
        case id, kind, t_ms, dur_ms, wall_ms, turn, text, path, meta
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        kind = EventKind(rawValue: (try? c.decode(String.self, forKey: .kind)) ?? "")
        t_ms = (try? c.decode(Int.self, forKey: .t_ms)) ?? 0
        dur_ms = (try? c.decode(Int.self, forKey: .dur_ms)) ?? 0
        wall_ms = (try? c.decode(Int.self, forKey: .wall_ms)) ?? 0
        turn = try? c.decode(Int.self, forKey: .turn)
        text = try? c.decode(String.self, forKey: .text)
        path = try? c.decode(String.self, forKey: .path)
        meta = (try? c.decode([String: JSONValue].self, forKey: .meta)) ?? [:]
    }

    var wall: Date { Date(timeIntervalSince1970: Double(wall_ms) / 1000) }
}

/// Whether the half that owns the pen is running. Without it the app
/// promises an answer that nothing is there to give.
nonisolated struct DiaryPresence: Codable, Sendable, Equatable {
    var present: Bool
    var ago_ms: Int?
    /// who runs that half on the server: a systemd user unit, or the server
    /// itself with a pidfile. A stop under systemd is a request to a
    /// supervisor, which is a weaker promise than a kill.
    var manager: String
    /// a start or stop asked from a page is still running
    var busy: Bool

    static let unknown = DiaryPresence(present: false, ago_ms: nil, manager: "here", busy: false)
}

/// Who is looking at the page on the tablet: somebody on Live, or nobody.
nonisolated enum Watcher: String, Codable, Sendable {
    case live
}

/// What the server says on /ws/events. Decoded by hand on `type`, so an
/// unknown message is `.unknown` rather than an error.
nonisolated enum ServerMessage: Sendable {
    case event(DiaryEvent)
    case hello(Hello)
    /// a send was recorded, and this is its id. The reply carries the same
    /// id in meta.intent, which is how an optimistic row settles.
    case intentOK(id: Int, atMs: Int)
    /// the loop came, went, or is being started or stopped
    case diary(DiaryPresence)
    case pong(Int)
    /// the switch was turned, from this app or another page
    case vanish(Bool)
    /// somebody opened the page on Live, or the last one left. While set the
    /// diary lets every pause go and refuses a send
    case watched(Watcher?)
    /// the gate opened or closed: somebody is speaking, or has stopped
    case hearing(Bool)
    /// a sentence is being read
    case pending(clip: String, on: Bool)
    case error(String)
    case unknown(String)

    nonisolated struct Hello: Decodable, Sendable {
        let session: Int
        let started_ms: Int
        let now_ms: Int
        let listening: Bool
        /// whether the server will stream the tablet's screen on /ws/live,
        /// which is RIDDLE_ALLOW_SNAP and nothing else
        let live: Bool?
        /// null until any page has set it, which the diary reads as yes
        let vanish: Bool?
        let watched: Watcher?
        let diary: DiaryPresence?
    }

    private struct Head: Decodable { let type: String }
    private struct IntentOK: Decodable { let id: Int; let at_ms: Int? }
    private struct Pong: Decodable { let t: Int? }
    private struct On: Decodable { let on: Bool }
    private struct By: Decodable { let by: Watcher? }
    private struct Pending: Decodable { let clip: String; let on: Bool }
    private struct Failure: Decodable { let message: String? }

    static func decode(_ data: Data) throws -> ServerMessage {
        let json = JSONDecoder()
        let type = try json.decode(Head.self, from: data).type
        switch type {
        case "event": return .event(try json.decode(DiaryEvent.self, from: data))
        case "hello.ok": return .hello(try json.decode(Hello.self, from: data))
        case "intent.ok":
            let it = try json.decode(IntentOK.self, from: data)
            return .intentOK(id: it.id, atMs: it.at_ms ?? 0)
        case "diary": return .diary(try json.decode(DiaryPresence.self, from: data))
        case "pong": return .pong(try json.decode(Pong.self, from: data).t ?? 0)
        case "vanish": return .vanish(try json.decode(On.self, from: data).on)
        case "watched": return .watched(try json.decode(By.self, from: data).by)
        case "hearing": return .hearing(try json.decode(On.self, from: data).on)
        case "pending":
            let it = try json.decode(Pending.self, from: data)
            return .pending(clip: it.clip, on: it.on)
        case "error": return .error(try json.decode(Failure.self, from: data).message ?? "something went wrong")
        default: return .unknown(type)
        }
    }
}

/// What the app says on /ws/events.
nonisolated enum ClientMessage: Sendable {
    case hello(since: Int, limit: Int)
    case ping(t: Int)
    case note(text: String)
    case send(atMs: Int, draft: String)
    /// the eraser: the diary rubs its ink off the page, forgets the
    /// conversation and deletes this session's rows. Not acknowledged; the
    /// `tool` row with meta.doing == "cleared" is what says it happened
    case clear
    /// the switch: fade and answer, or leave the page alone
    case vanish(on: Bool)
    /// bring the half that owns the pen up, or take it down. Not
    /// acknowledged: `diary` is what says it arrived
    case diaryStart
    case diaryStop

    var json: String {
        let body: [String: Any] = switch self {
        case let .hello(since, limit): ["type": "hello", "since": since, "limit": limit]
        case let .ping(t): ["type": "ping", "t": t]
        case let .note(text): ["type": "note", "text": text]
        case let .send(atMs, draft): ["type": "send", "at_ms": atMs, "draft": draft]
        case .clear: ["type": "clear"]
        case let .vanish(on): ["type": "vanish", "on": on]
        case .diaryStart: ["type": "diary.start"]
        case .diaryStop: ["type": "diary.stop"]
        }
        let data = (try? JSONSerialization.data(withJSONObject: body)) ?? Data("{}".utf8)
        return String(decoding: data, as: UTF8.self)
    }
}

/// The text half of /ws/live; the binary half is one png per changed frame.
/// `dialing` until the tablet answers, `on` while frames arrive, `lost` when
/// the link dropped and the server is redialling by itself.
nonisolated struct LiveMessage: Decodable, Sendable {
    let type: String
    let state: String
    let message: String?
}

/// What the model made of a page: `POST /api/understand`.
nonisolated struct Understanding: Codable, Sendable, Equatable {
    let title: String
    let kind: String
    let summary: String
    let points: [String]
    let transcript: String
    let model: String
    let took_ms: Int
}

/// What `POST /api/library` answers once the document is in.
nonisolated struct LibraryEntry: Decodable, Sendable {
    let id: String
    let name: String
}
