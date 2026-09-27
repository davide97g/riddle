import Foundation
import Observation

/// Which server this app talks to, as the person set it up.
///
/// The address lives in defaults and the token in the keychain. Until both
/// are there and the server has said yes to them, the app shows the setup
/// screen and opens no socket.
@Observable
final class Connection {
    private static let addressKey = "riddle.server"
    private static let tokenKey = "token"

    private(set) var server: Server?

    init() {
        if let typed = UserDefaults.standard.string(forKey: Self.addressKey),
           let base = Server.parse(typed) {
            server = Server(base: base, token: Keychain.read(Self.tokenKey))
        }
    }

    var address: String { server?.base.absoluteString ?? "" }

    /// Try an address and a password, and keep them only if the server lets
    /// them in. An empty password is a server with no gate.
    func connect(address: String, password: String) async throws {
        guard let base = Server.parse(address) else {
            throw ServerError.said("that is not an address: try 192.168.1.20:8765")
        }
        let token = password.isEmpty ? nil : Server.mint(password)
        let next = Server(base: base, token: token)
        try await API.check(next)
        UserDefaults.standard.set(base.absoluteString, forKey: Self.addressKey)
        Keychain.write(Self.tokenKey, token)
        server = next
    }

    func forget() {
        UserDefaults.standard.removeObject(forKey: Self.addressKey)
        Keychain.write(Self.tokenKey, nil)
        server = nil
    }
}
