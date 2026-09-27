import SwiftUI

/// Where the voice server is and its password, asked once. Nothing is kept
/// until the server has said yes to both.
struct ServerForm: View {
    @Environment(Connection.self) private var connection
    @State private var address = ""
    @State private var password = ""
    @State private var trying = false
    @State private var failure: String?
    var done: () -> Void = {}

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Server").font(.caption).foregroundStyle(.secondary)
                TextField("192.168.1.20:8765", text: $address)
                    .textFieldStyle(.roundedBorder)
                    .autocorrectionDisabled()
                    #if os(iOS)
                    .textInputAutocapitalization(.never)
                    .keyboardType(.URL)
                    #endif
                    .onSubmit(connect)
            }
            VStack(alignment: .leading, spacing: 6) {
                Text("Password").font(.caption).foregroundStyle(.secondary)
                SecureField("RIDDLE_WEB_PASSWORD, if it has one", text: $password)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit(connect)
            }
            if let failure {
                Text(failure).font(.callout).foregroundStyle(.red)
            }
            Text("The address `riddle voice start` prints, the tailnet name `riddle voice share` gives, or the tunnel's https url. The password is kept only as the cookie it makes.")
                .font(.caption)
                .foregroundStyle(.secondary)
            Button(action: connect) {
                HStack {
                    if trying { ProgressView().controlSize(.small) }
                    Text(trying ? "Connecting…" : "Connect")
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(trying || address.trimmingCharacters(in: .whitespaces).isEmpty)
        }
        .onAppear { if address.isEmpty { address = connection.address } }
    }

    private func connect() {
        guard !trying else { return }
        trying = true
        failure = nil
        Task {
            do {
                try await connection.connect(address: address, password: password)
                password = ""
                done()
            } catch {
                failure = error.localizedDescription
            }
            trying = false
        }
    }
}

struct SetupView: View {
    var body: some View {
        ScrollView {
            VStack(spacing: 28) {
                Wordmark(duration: 1.6)
                    .frame(height: 44)
                    .padding(.top, 60)
                Text("A diary that answers on the tablet.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                ServerForm()
                    .frame(maxWidth: 380)
            }
            .padding(24)
            .frame(maxWidth: .infinity)
        }
    }
}

/// The same form, for a server already set up: in Settings on the Mac and
/// behind the gear on the iPhone.
struct ServerSettings: View {
    @Environment(Connection.self) private var connection
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            if connection.server != nil {
                LabeledContent("Connected to", value: connection.address)
            }
            ServerForm { dismiss() }
            if connection.server != nil {
                Divider()
                Button("Forget this server", role: .destructive) {
                    connection.forget()
                    dismiss()
                }
            }
        }
    }
}
