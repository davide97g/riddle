import SwiftUI
#if os(macOS)
import AppKit
typealias PlatformImage = NSImage
#else
import UIKit
typealias PlatformImage = UIImage
#endif

extension Image {
    init(platform image: PlatformImage) {
        #if os(macOS)
        self.init(nsImage: image)
        #else
        self.init(uiImage: image)
        #endif
    }
}

enum Clipboard {
    static func png(_ data: Data) {
        #if os(macOS)
        let board = NSPasteboard.general
        board.clearContents()
        board.setData(data, forType: .png)
        #else
        UIPasteboard.general.setData(data, forPasteboardType: "public.png")
        #endif
    }

    static func text(_ text: String) {
        #if os(macOS)
        let board = NSPasteboard.general
        board.clearContents()
        board.setString(text, forType: .string)
        #else
        UIPasteboard.general.string = text
        #endif
    }
}

extension Color {
    /// The one colour on an otherwise grey page: something is live. The same
    /// emerald as the page's `--live`.
    static let live = Color(red: 0.13, green: 0.72, blue: 0.51)
}

/// How a picture of the page is shown.
///
/// `paper` is the page as it is: white paper, black ink, in either theme.
/// `ink` drops the paper and lets the ink sit on the theme -- which in the
/// dark theme is a negative, right for handwriting and wrong for a
/// photograph or a pdf. Paper is the default.
enum Look: String {
    case paper, ink
}

struct LookModifier: ViewModifier {
    let look: Look
    @Environment(\.colorScheme) private var scheme

    func body(content: Content) -> some View {
        if look == .paper {
            content
        } else if scheme == .dark {
            // Invert first so the ink is white, then screen drops the black.
            content.colorInvert().blendMode(.screen)
        } else {
            content.blendMode(.multiply)
        }
    }
}

extension View {
    func look(_ look: Look) -> some View { modifier(LookModifier(look: look)) }
}

extension Date {
    var clock: String { formatted(date: .omitted, time: .standard) }
}
