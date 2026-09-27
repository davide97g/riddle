import AVFoundation
import Foundation
import Observation
#if os(macOS)
import CoreAudio
#endif

/// A microphone the person can pick. `id` is what the system calls it
/// across launches: a port uid on iOS, a device uid on the Mac.
struct MicInput: Identifiable, Hashable {
    let id: String
    let name: String
}

/// The microphone, from the button press to the last frame on the wire.
///
/// Opening /ws/audio is what starts a recording and closing it is what ends
/// one, so there is no start or stop message that can fall out of step with
/// what the microphone is actually doing. Frames are 4 bytes of
/// little-endian sequence number, then 3200 int16 samples at 16 kHz mono --
/// 200 ms -- which is what the page's worklet sends too.
@Observable
final class Microphone {
    enum State { case idle, requesting, recording, stopping }

    private static let chosenKey = "riddle.mic"

    private(set) var state: State = .idle
    /// RMS of the last ~50 ms, 0...1, for the meter
    private(set) var level: Float = 0
    private(set) var inputs: [MicInput] = []
    /// the one the person chose, or nil for the system default
    var chosen: String? {
        didSet { UserDefaults.standard.set(chosen, forKey: Self.chosenKey) }
    }
    /// the newest reason it stopped or would not start, for a toast
    var failure: String?

    private var engine: AVAudioEngine?
    private var pipe: AudioPipe?

    init() {
        chosen = UserDefaults.standard.string(forKey: Self.chosenKey)
        refresh()
    }

    func refresh() {
        inputs = Self.listInputs()
        if let chosen, !inputs.contains(where: { $0.id == chosen }) {
            // The remembered microphone was unplugged between launches. The
            // system default it is, rather than refusing to listen at all.
            self.chosen = nil
        }
    }

    func start(_ server: Server) async {
        guard state == .idle else { return }
        state = .requesting
        guard await AVAudioApplication.requestRecordPermission() else {
            state = .idle
            failure = "The microphone was refused. Allow it in System Settings, under Privacy."
            return
        }
        do {
            try await begin(server)
            state = .recording
        } catch {
            teardown()
            state = .idle
            failure = "Could not start listening: \(error.localizedDescription)"
        }
    }

    func stop() {
        guard state == .recording else { return }
        state = .stopping
        // A clean close is the signal to transcribe the tail of what was said.
        pipe?.finish()
        teardown()
        state = .idle
    }

    private func begin(_ server: Server) async throws {
        #if os(iOS)
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.record, mode: .default)
        if let chosen, let port = session.availableInputs?.first(where: { $0.uid == chosen }) {
            try? session.setPreferredInput(port)
        }
        try session.setActive(true)
        #endif

        let engine = AVAudioEngine()
        #if os(macOS)
        if let chosen, var device = Self.deviceID(uid: chosen), let unit = engine.inputNode.audioUnit {
            AudioUnitSetProperty(unit, kAudioOutputUnitProperty_CurrentDevice, kAudioUnitScope_Global, 0,
                                 &device, UInt32(MemoryLayout<AudioDeviceID>.size))
        }
        #endif
        let input = engine.inputNode.outputFormat(forBus: 0)
        guard input.sampleRate > 0, input.channelCount > 0 else {
            throw ServerError.said("there is no microphone to listen on")
        }

        let capture = String(UUID().uuidString.prefix(8)).lowercased()
        let sock = API.session.webSocketTask(with: server.socket(
            "/ws/audio", query: ["capture": capture, "rate": "16000", "frame": "3200"]))
        sock.resume()
        // A ping that comes back is the handshake done and the gate passed:
        // the socket has no other way to say it is open.
        try await withCheckedThrowingContinuation { (done: CheckedContinuation<Void, Error>) in
            sock.sendPing { error in
                if let error { done.resume(throwing: error) } else { done.resume() }
            }
        }

        let pipe = try AudioPipe(from: input, socket: sock) { [weak self] level in
            Task { @MainActor in self?.level = level }
        }
        engine.inputNode.installTap(onBus: 0, bufferSize: 2048, format: input, block: pipe.tap)
        engine.prepare()
        try engine.start()
        self.engine = engine
        self.pipe = pipe
        refresh()

        // Never reconnect a recording. A gap in the audio would be stitched
        // silently into a sentence nobody said.
        Task { [weak self] in
            while true {
                do { _ = try await sock.receive() } catch { break }
            }
            guard let self, self.pipe === pipe, self.state == .recording else { return }
            self.teardown()
            self.state = .idle
            let why = sock.closeReason.map { String(decoding: $0, as: UTF8.self) }
            self.failure = "Recording interrupted" + (why.map { ": \($0)" } ?? "")
        }
    }

    private func teardown() {
        engine?.inputNode.removeTap(onBus: 0)
        engine?.stop()
        engine = nil
        pipe?.hangUp()
        pipe = nil
        level = 0
        #if os(iOS)
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        #endif
    }

    // MARK: which microphones there are

    private static func listInputs() -> [MicInput] {
        #if os(iOS)
        let session = AVAudioSession.sharedInstance()
        return (session.availableInputs ?? []).map { MicInput(id: $0.uid, name: $0.portName) }
        #else
        return inputDevices().map { MicInput(id: $0.uid, name: $0.name) }
        #endif
    }

    #if os(macOS)
    private static func deviceID(uid: String) -> AudioDeviceID? {
        inputDevices().first { $0.uid == uid }?.id
    }

    private static func inputDevices() -> [(id: AudioDeviceID, uid: String, name: String)] {
        var address = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDevices,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain)
        var size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size) == noErr
        else { return [] }
        var ids = [AudioDeviceID](repeating: 0, count: Int(size) / MemoryLayout<AudioDeviceID>.size)
        guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &ids) == noErr
        else { return [] }
        return ids.compactMap { id in
            var streams = AudioObjectPropertyAddress(
                mSelector: kAudioDevicePropertyStreams,
                mScope: kAudioDevicePropertyScopeInput,
                mElement: kAudioObjectPropertyElementMain)
            var count: UInt32 = 0
            guard AudioObjectGetPropertyDataSize(id, &streams, 0, nil, &count) == noErr, count > 0 else { return nil }
            guard let uid = string(id, kAudioDevicePropertyDeviceUID),
                  let name = string(id, kAudioObjectPropertyName) else { return nil }
            return (id, uid, name)
        }
    }

    private static func string(_ id: AudioObjectID, _ selector: AudioObjectPropertySelector) -> String? {
        var address = AudioObjectPropertyAddress(
            mSelector: selector,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain)
        var value: Unmanaged<CFString>?
        var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        guard AudioObjectGetPropertyData(id, &address, 0, nil, &size, &value) == noErr,
              let value else { return nil }
        return value.takeRetainedValue() as String
    }
    #endif
}

/// Everything that runs on the audio thread: resample to 16 kHz mono int16,
/// cut into 200 ms frames, number them and put them on the wire.
///
/// Off the main actor on purpose: a SwiftUI render, a socket callback or a
/// layout pass on the main thread must not be able to drop samples here.
nonisolated final class AudioPipe: @unchecked Sendable {
    static let rate = 16_000.0
    static let frameSamples = 3200
    /// ~50 ms, so the meter moves at 20 fps
    static let levelSamples = 800
    /// Frames on the wire and not yet sent. Past this they are dropped
    /// rather than queued: a frame that arrives late is a frame in the
    /// wrong sentence.
    static let maxInFlight = 8

    private let converter: AVAudioConverter
    private let output: AVAudioFormat
    private let socket: URLSessionWebSocketTask
    private let onLevel: @Sendable (Float) -> Void
    private let lock = NSLock()
    private var pending: [Int16] = []
    private var seq: UInt32 = 0
    private var inFlight = 0
    private var sumsq: Float = 0
    private var levelN = 0
    private var done = false

    init(from input: AVAudioFormat, socket: URLSessionWebSocketTask,
         onLevel: @escaping @Sendable (Float) -> Void) throws {
        guard let output = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: Self.rate,
                                         channels: 1, interleaved: true),
              let converter = AVAudioConverter(from: input, to: output) else {
            throw ServerError.said("this microphone's format cannot be turned into 16 kHz")
        }
        converter.downmix = true
        self.output = output
        self.converter = converter
        self.socket = socket
        self.onLevel = onLevel
        pending.reserveCapacity(Self.frameSamples * 2)
    }

    /// The tap. Called on the engine's own thread, never the main one.
    var tap: AVAudioNodeTapBlock {
        { [self] buffer, _ in convert(buffer) }
    }

    private func convert(_ buffer: AVAudioPCMBuffer) {
        let ratio = Self.rate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 32
        guard let out = AVAudioPCMBuffer(pcmFormat: output, frameCapacity: capacity) else { return }
        var given = false
        var error: NSError?
        converter.convert(to: out, error: &error) { _, status in
            if given {
                status.pointee = .noDataNow
                return nil
            }
            given = true
            status.pointee = .haveData
            return buffer
        }
        guard error == nil, let samples = out.int16ChannelData?[0] else { return }
        let n = Int(out.frameLength)

        lock.lock()
        defer { lock.unlock() }
        if done { return }
        for i in 0..<n {
            let s = samples[i]
            pending.append(s)
            let v = Float(s) / 32768
            sumsq += v * v
            levelN += 1
            if levelN == Self.levelSamples {
                onLevel(min(1, (sumsq / Float(levelN)).squareRoot()))
                sumsq = 0
                levelN = 0
            }
        }
        while pending.count >= Self.frameSamples {
            ship(Array(pending.prefix(Self.frameSamples)))
            pending.removeFirst(Self.frameSamples)
        }
    }

    /// Four byte little-endian frame index, then int16le pcm. The index is
    /// what places a sentence where it was spoken rather than where it
    /// happened to arrive, and a dropped frame is still counted.
    private func ship(_ frame: [Int16]) {
        var data = Data(capacity: 4 + frame.count * 2)
        withUnsafeBytes(of: seq.littleEndian) { data.append(contentsOf: $0) }
        seq &+= 1
        frame.withUnsafeBufferPointer { raw in
            for s in raw { withUnsafeBytes(of: s.littleEndian) { data.append(contentsOf: $0) } }
        }
        guard inFlight < Self.maxInFlight else { return }
        inFlight += 1
        socket.send(.data(data)) { [self] _ in
            lock.lock()
            inFlight -= 1
            lock.unlock()
        }
    }

    /// The end of a recording, said properly.
    func finish() {
        lock.lock()
        done = true
        lock.unlock()
        socket.cancel(with: .normalClosure, reason: Data("done".utf8))
    }

    func hangUp() {
        lock.lock()
        let was = done
        done = true
        lock.unlock()
        if !was { socket.cancel(with: .goingAway, reason: nil) }
    }
}
