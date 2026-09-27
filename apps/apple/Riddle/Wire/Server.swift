import CryptoKit
import Foundation
import Security

/// Where the voice server is, and the cookie that lets this app past its
/// gate.
///
/// The browser logs in with a form and gets a cookie back; the cookie is
/// `hmac(password, "riddle-v1")` and nothing else (riddle/web/auth.py), so
/// the app mints the same token itself and never keeps the password. It is
/// sent as the `riddle` cookie on every request and on every socket's
/// upgrade, which is the only thing the gate reads.
nonisolated struct Server: Sendable, Equatable {
    var base: URL
    /// nil when the server has no password, which is the loopback case
    var token: String?

    static func mint(_ password: String) -> String {
        let mac = HMAC<SHA256>.authenticationCode(
            for: Data("riddle-v1".utf8), using: SymmetricKey(data: Data(password.utf8)))
        return mac.map { String(format: "%02x", $0) }.joined()
    }

    /// Anything typed into the address field, made into a base url:
    /// `192.168.1.20:8765` is as good as `http://192.168.1.20:8765/`.
    static func parse(_ typed: String) -> URL? {
        var text = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        if text.isEmpty { return nil }
        if !text.contains("://") { text = "http://" + text }
        guard var parts = URLComponents(string: text), parts.host?.isEmpty == false,
              parts.scheme == "http" || parts.scheme == "https" else { return nil }
        parts.path = ""
        parts.query = nil
        parts.fragment = nil
        return parts.url
    }

    func request(_ path: String, query: [String: String] = [:], method: String = "GET") -> URLRequest {
        var parts = URLComponents(url: base, resolvingAgainstBaseURL: false)!
        parts.path = path
        if !query.isEmpty { parts.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) } }
        var req = URLRequest(url: parts.url!)
        req.httpMethod = method
        authorise(&req)
        return req
    }

    /// The same request for a socket: `ws` for `http`, `wss` for `https`.
    func socket(_ path: String, query: [String: String] = [:]) -> URLRequest {
        var req = request(path, query: query)
        var parts = URLComponents(url: req.url!, resolvingAgainstBaseURL: false)!
        parts.scheme = parts.scheme == "https" ? "wss" : "ws"
        req.url = parts.url
        return req
    }

    private func authorise(_ req: inout URLRequest) {
        // Set by hand and kept out of the shared jar: two servers typed in
        // one after the other must not both answer to whichever cookie the
        // jar thinks belongs to the host.
        req.httpShouldHandleCookies = false
        if let token { req.setValue("riddle=\(token)", forHTTPHeaderField: "Cookie") }
    }
}

nonisolated enum ServerError: LocalizedError {
    case locked
    case said(String)
    case status(Int)

    var errorDescription: String? {
        switch self {
        case .locked: "the server wants a password, and this is not it"
        case let .said(text): text
        case let .status(code): "the server answered \(code)"
        }
    }
}

/// The handful of http calls the app makes. Everything else is a socket.
nonisolated enum API {
    static let session: URLSession = {
        let config = URLSessionConfiguration.default
        config.httpCookieStorage = nil
        config.httpShouldSetCookies = false
        config.timeoutIntervalForRequest = 30
        // A library push restarts xochitl and answers once it is back.
        config.timeoutIntervalForResource = 180
        return URLSession(configuration: config)
    }()

    static func call(_ req: URLRequest) async throws -> Data {
        let (data, response) = try await session.data(for: req)
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        if (200..<300).contains(code) { return data }
        let said = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        if code == 401 { throw ServerError.locked }
        if let text = said?["error"] as? String { throw ServerError.said(text) }
        throw ServerError.status(code)
    }

    /// Whether the server is there and lets this token in. `/api/health` is
    /// the one route outside the gate, so it says the first and `/api/state`
    /// the second.
    static func check(_ server: Server) async throws {
        _ = try await call(server.request("/api/health"))
        _ = try await call(server.request("/api/state"))
    }

    /// Put a file in the tablet's library: one request, which restarts
    /// xochitl on the way.
    static func library(_ server: Server, file: Data, type: String, name: String) async throws -> LibraryEntry {
        var req = server.request("/api/library", query: ["name": name], method: "POST")
        req.setValue(type, forHTTPHeaderField: "Content-Type")
        req.timeoutInterval = 180
        let (data, response) = try await session.upload(for: req, from: file)
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else {
            let said = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            if code == 401 { throw ServerError.locked }
            throw (said?["error"] as? String).map(ServerError.said) ?? ServerError.status(code)
        }
        return try JSONDecoder().decode(LibraryEntry.self, from: data)
    }

    /// Ask what is on a snapshot. The snapshot's own png is sent, never a
    /// fresh read of the tablet.
    static func understand(_ server: Server, png: Data) async throws -> Understanding {
        var req = server.request("/api/understand", method: "POST")
        req.setValue("image/png", forHTTPHeaderField: "Content-Type")
        req.httpBody = png
        req.timeoutInterval = 120
        return try JSONDecoder().decode(Understanding.self, from: try await call(req))
    }

    /// `/api/captures/<name>` serves one file out of `var/captures`, so only
    /// the name goes in the url. Older rows spell the path from the checkout
    /// root, so the last segment is taken rather than trusting a prefix.
    static func capture(_ server: Server, path: String) async throws -> Data {
        let name = path.split(separator: "/").last.map(String.init) ?? path
        let escaped = name.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? name
        return try await call(server.request("/api/captures/\(escaped)"))
    }
}

/// The token, in the keychain rather than in defaults: it is as good as the
/// password for as long as the password stays the same.
nonisolated enum Keychain {
    private static let service = "com.davide97g.riddle"

    static func read(_ account: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
        ]
        var out: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &out) == errSecSuccess,
              let data = out as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func write(_ account: String, _ value: String?) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
        guard let value else { return }
        var item = query
        item[kSecValueData as String] = Data(value.utf8)
        item[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(item as CFDictionary, nil)
    }
}
