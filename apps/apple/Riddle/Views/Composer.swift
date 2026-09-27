import SwiftUI

/// What you can say to the diary: the microphone, a typed line, and Send.
struct Composer: View {
    @Environment(Diary.self) private var diary
    @Environment(Connection.self) private var connection
    @Environment(Microphone.self) private var mic
    @Environment(Toasts.self) private var toasts
    @Environment(\.horizontalSizeClass) private var width
    @FocusState private var typing: Bool

    var body: some View {
        @Bindable var diary = diary
        let offline = diary.conn != .open
        let canSend = !offline && diary.diary.present && diary.vanish && diary.watched == nil

        VStack(spacing: 8) {
            HStack(alignment: .bottom, spacing: 8) {
                MicButton(disabled: offline || !diary.listening)
                TextField(mic.state == .recording ? "listening…" : "say something to the diary",
                          text: $diary.draft, axis: .vertical)
                    .lineLimit(1...5)
                    .textFieldStyle(.plain)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .background(.background.secondary, in: .rect(cornerRadius: 12))
                    .overlay {
                        RoundedRectangle(cornerRadius: 12)
                            .strokeBorder(Color.primary.opacity(typing ? 0.25 : 0.1))
                    }
                    .focused($typing)
                    #if os(iOS)
                    .submitLabel(.send)
                    #endif
                Button("Send") { diary.send() }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .disabled(!canSend)
                    .keyboardShortcut(.return, modifiers: .command)
            }
            // On a phone the switch and the microphone live in the gear
            // menu, and the line under the row only speaks when something
            // is off: a footer that explains itself while everything works
            // is a footer in the way.
            let compact = width == .compact
            if !compact { VanishToggle() }
            if mic.state == .recording { LevelMeter(level: mic.level) }
            if !compact, diary.listening { MicPicker(disabled: mic.state != .idle) }
            if let said = compact ? problem : (problem ?? Self.fine) {
                Text(said)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .contentTransition(.opacity)
                    .animation(.easeOut, value: said)
            }
        }
        .frame(maxWidth: 680)
        .padding(.horizontal, 16)
        .padding(.top, 10)
        .padding(.bottom, width == .compact ? 8 : 12)
        .frame(maxWidth: .infinity)
        .background(.bar)
        .onChange(of: mic.failure) { _, said in
            guard let said else { return }
            toasts.failure(said)
            mic.failure = nil
        }
    }

    private static let fine = "Send asks the diary for an answer now. It always answers on the tablet."

    /// Why you cannot send, or cannot speak, if anything is in the way.
    private var problem: String? {
        if !diary.vanish { return "Vanishing is off: what you write stays on the page, and the diary does not answer." }
        if diary.watched == .live { return "The page is open on Live, so the diary leaves it alone. Close Live to write to it." }
        if !diary.diary.present { return "The diary is not running, so nothing would answer a send." }
        if !diary.listening { return "No speech model loaded, so the microphone is off." }
        return nil
    }
}

struct MicButton: View {
    let disabled: Bool
    @Environment(Microphone.self) private var mic
    @Environment(Connection.self) private var connection

    var body: some View {
        let recording = mic.state == .recording
        // `stopping` is not decoration: closing the socket and reading the
        // tail of the sentence takes a moment.
        let busy = mic.state == .requesting || mic.state == .stopping
        Button {
            if recording { mic.stop() } else if let server = connection.server {
                Task { await mic.start(server) }
            }
        } label: {
            Image(systemName: recording ? "stop.fill" : "mic.fill")
                .font(.system(size: 17, weight: .semibold))
                .contentTransition(.symbolEffect(.replace))
                .frame(width: 44, height: 44)
                .foregroundStyle(recording ? Color.white : Color.primary)
                .background(recording ? Color.live : Color.secondary.opacity(0.18), in: .circle)
                .overlay {
                    if recording {
                        Circle().strokeBorder(Color.live.opacity(0.5), lineWidth: 2).padding(-4)
                            .phaseAnimator([1.0, 1.12]) { ring, grow in
                                ring.scaleEffect(grow).opacity(2 - grow * 1.5)
                            } animation: { _ in .easeInOut(duration: 0.9) }
                    }
                }
        }
        .buttonStyle(.plain)
        .disabled(disabled || busy)
        .opacity(disabled ? 0.4 : busy ? 0.6 : 1)
        .accessibilityLabel(recording ? "Stop listening" : "Start listening")
    }
}

struct LevelMeter: View {
    let level: Float

    var body: some View {
        GeometryReader { box in
            Capsule().fill(.quaternary)
                .overlay(alignment: .leading) {
                    // Speech sits around 0.02-0.2 RMS, so the scale is lifted
                    // until a normal voice fills most of the bar.
                    Capsule().fill(Color.live)
                        .frame(width: box.size.width * CGFloat(min(1, sqrt(Double(level)) * 1.8)))
                        .animation(.linear(duration: 0.05), value: level)
                }
        }
        .frame(width: 160, height: 4)
        .accessibilityHidden(true)
    }
}

/// Which microphone the next recording opens. Changing it mid-recording
/// would splice two rooms into one sentence, so it waits.
struct MicPicker: View {
    let disabled: Bool
    @Environment(Microphone.self) private var mic

    var body: some View {
        @Bindable var mic = mic
        Menu {
            Picker("Microphone", selection: $mic.chosen) {
                Text("System default").tag(String?.none)
                ForEach(mic.inputs) { input in Text(input.name).tag(Optional(input.id)) }
            }
            Divider()
            Button("Look again") { mic.refresh() }
        } label: {
            Label(mic.inputs.first { $0.id == mic.chosen }?.name ?? "System default microphone",
                  systemImage: "mic")
                .font(.caption)
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .foregroundStyle(.secondary)
        .fixedSize()
        .disabled(disabled)
    }
}

/// The trick itself, on or off. On, a pause of three seconds is a question:
/// your ink fades and the diary writes back. Off, a pause is only a pause
/// and what you write stays where you wrote it.
struct VanishToggle: View {
    @Environment(Diary.self) private var diary

    var body: some View {
        Toggle(isOn: Binding(get: { diary.vanish }, set: { diary.setVanish($0) })) {
            Text("Vanish and answer").font(.caption)
        }
        .toggleStyle(.switch)
        .controlSize(.mini)
        .fixedSize()
        .disabled(diary.conn != .open)
        .accessibilityHint(diary.vanish
            ? "After a pause your writing fades and the diary answers."
            : "Your writing stays on the page and the diary does not answer.")
    }
}
