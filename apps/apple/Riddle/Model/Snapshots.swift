import Foundation
import Observation

/// One kept frame, and what the model made of it once asked.
struct Snapshot: Codable, Identifiable, Equatable {
    let id: UUID
    let at: Date
    var understood: Understanding?

    /// `riddle-2026-09-25-153207.png`, in this device's own time zone.
    var fileName: String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd-HHmmss"
        return "riddle-\(f.string(from: at)).png"
    }
}

/// The last ten frames somebody chose to keep, newest first.
///
/// On this device and nowhere else: the server never learns a snapshot was
/// taken, and the frame is the png it already sent, so nothing is read off
/// the tablet twice. Kept as files in Application Support rather than in
/// defaults, because a dense page is a couple of hundred kilobytes.
@Observable
final class Snapshots {
    enum Reading: Equatable { case reading, failed(String) }

    static let max = 10

    private(set) var list: [Snapshot] = []
    /// a reading in flight, or why the last one failed. Not kept
    private(set) var reading: [UUID: Reading] = [:]

    private let dir: URL = {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        let dir = base.appending(path: "Snapshots", directoryHint: .isDirectory)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }()

    private var index: URL { dir.appending(path: "index.json") }

    init() {
        if let data = try? Data(contentsOf: index),
           let kept = try? JSONDecoder().decode([Snapshot].self, from: data) {
            list = kept.filter { FileManager.default.fileExists(atPath: file($0).path) }
        }
    }

    func file(_ snap: Snapshot) -> URL { dir.appending(path: "\(snap.id.uuidString).png") }

    func png(_ snap: Snapshot) -> Data? { try? Data(contentsOf: file(snap)) }

    @discardableResult
    func take(_ png: Data) -> Snapshot? {
        let snap = Snapshot(id: UUID(), at: Date())
        do { try png.write(to: file(snap), options: .atomic) } catch { return nil }
        keep([snap] + list)
        return snap
    }

    func remove(_ snap: Snapshot) {
        keep(list.filter { $0.id != snap.id })
    }

    /// Ask the model what is on one snapshot, and keep the answer with it.
    /// The snapshot's own png is sent, so an old one is understood as it
    /// was when it was taken.
    func understand(_ snap: Snapshot, server: Server) async {
        guard let png = png(snap) else { return }
        reading[snap.id] = .reading
        do {
            let said = try await API.understand(server, png: png)
            // Deleted while it was being read: nothing left to keep it with.
            if list.contains(where: { $0.id == snap.id }) {
                keep(list.map { $0.id == snap.id ? Snapshot(id: $0.id, at: $0.at, understood: said) : $0 })
            }
            reading[snap.id] = nil
        } catch {
            reading[snap.id] = .failed(error.localizedDescription)
        }
    }

    private func keep(_ next: [Snapshot]) {
        let kept = Array(next.prefix(Self.max))
        for gone in list where !kept.contains(where: { $0.id == gone.id }) {
            try? FileManager.default.removeItem(at: file(gone))
        }
        list = kept
        if let data = try? JSONEncoder().encode(kept) { try? data.write(to: index, options: .atomic) }
    }
}
