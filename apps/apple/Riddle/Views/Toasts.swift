import Observation
import SwiftUI

/// One line at the top of the window that says how something went, and
/// goes away by itself. The page's sonner, reduced to what it is used for.
@Observable
final class Toasts {
    struct Toast: Identifiable, Equatable {
        enum Kind { case success, info, warning, failure }
        let id = UUID()
        let kind: Kind
        let title: String
        let detail: String?
    }

    private(set) var shown: [Toast] = []

    func say(_ title: String, _ detail: String? = nil, kind: Toast.Kind = .info) {
        let toast = Toast(kind: kind, title: title, detail: detail)
        withAnimation(.snappy) { shown = Array((shown + [toast]).suffix(3)) }
        Task { [weak self] in
            try? await Task.sleep(for: .seconds(kind == .failure ? 6 : 4))
            withAnimation(.snappy) { self?.shown.removeAll { $0.id == toast.id } }
        }
    }

    func success(_ title: String, _ detail: String? = nil) { say(title, detail, kind: .success) }
    func warning(_ title: String, _ detail: String? = nil) { say(title, detail, kind: .warning) }
    func failure(_ title: String, _ detail: String? = nil) { say(title, detail, kind: .failure) }

    func dismiss(_ toast: Toast) {
        withAnimation(.snappy) { shown.removeAll { $0.id == toast.id } }
    }
}

struct ToastStack: View {
    @Environment(Toasts.self) private var toasts

    var body: some View {
        VStack(spacing: 8) {
            ForEach(toasts.shown) { toast in
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Image(systemName: symbol(toast.kind))
                        .foregroundStyle(tint(toast.kind))
                    VStack(alignment: .leading, spacing: 2) {
                        Text(toast.title).font(.callout.weight(.medium))
                        if let detail = toast.detail {
                            Text(detail).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .frame(maxWidth: 420)
                .glassEffect(.regular, in: .rect(cornerRadius: 14))
                .onTapGesture { toasts.dismiss(toast) }
                .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .padding(.top, 8)
        .padding(.horizontal, 16)
        .frame(maxWidth: .infinity)
    }

    private func symbol(_ kind: Toasts.Toast.Kind) -> String {
        switch kind {
        case .success: "checkmark.circle.fill"
        case .info: "info.circle.fill"
        case .warning: "exclamationmark.triangle.fill"
        case .failure: "xmark.octagon.fill"
        }
    }

    private func tint(_ kind: Toasts.Toast.Kind) -> Color {
        switch kind {
        case .success: .live
        case .info: .secondary
        case .warning: .orange
        case .failure: .red
        }
    }
}
