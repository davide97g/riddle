import SwiftUI

/// The word "riddle" in the diary's own hand, drawn the way the machine
/// would draw it: stroke by stroke, left to right, at one speed.
struct Wordmark: View {
    /// how long the nib takes over the whole word; 0 draws it at once
    var duration: Double = 0
    @State private var drawn: CGFloat = 0

    var body: some View {
        GeometryReader { box in
            let scale = min(box.size.width / WordmarkData.width, box.size.height / WordmarkData.height)
            WordmarkShape(drawn: drawn)
                .stroke(style: StrokeStyle(lineWidth: WordmarkData.nib * scale * 0.9,
                                           lineCap: .round, lineJoin: .round))
        }
        .aspectRatio(WordmarkData.width / WordmarkData.height, contentMode: .fit)
        .accessibilityElement()
        .accessibilityLabel("riddle")
        .onAppear {
            guard drawn == 0 else { return }
            if duration > 0 {
                withAnimation(.linear(duration: duration)) { drawn = 1 }
            } else {
                drawn = 1
            }
        }
    }
}

/// The centre lines of the strokes, trimmed to how far the nib has got.
nonisolated struct WordmarkShape: Shape {
    var drawn: CGFloat

    private static let paths: [Path] = WordmarkData.strokes.map { SVGPath.parse($0.d) }
    private static let total: CGFloat = WordmarkData.strokes.reduce(0) { $0 + $1.len }

    var animatableData: CGFloat {
        get { drawn }
        set { drawn = newValue }
    }

    func path(in rect: CGRect) -> Path {
        let nib = WordmarkData.nib
        let scale = min(rect.width / (WordmarkData.width + nib), rect.height / (WordmarkData.height + nib))
        let place = CGAffineTransform(translationX: rect.minX + nib / 2 * scale, y: rect.minY + nib / 2 * scale)
            .scaledBy(x: scale, y: scale)
        var out = Path()
        var travelled: CGFloat = 0
        for (i, stroke) in WordmarkData.strokes.enumerated() {
            let start = travelled / Self.total
            travelled += stroke.len
            let end = travelled / Self.total
            let part = drawn <= start ? 0 : drawn >= end ? 1 : (drawn - start) / (end - start)
            guard part > 0 else { continue }
            out.addPath(Self.paths[i].trimmedPath(from: 0, to: part).applying(place))
        }
        return out
    }
}

/// Just enough of the svg path grammar for the wordmark: absolute M, L and
/// C, which is all the generator ever writes.
nonisolated enum SVGPath {
    static func parse(_ d: String) -> Path {
        var path = Path()
        var numbers: [CGFloat] = []
        var command: Character = "M"
        func flush() {
            switch command {
            case "M" where numbers.count >= 2:
                path.move(to: CGPoint(x: numbers[0], y: numbers[1]))
                var rest = Array(numbers.dropFirst(2))
                while rest.count >= 2 {
                    path.addLine(to: CGPoint(x: rest[0], y: rest[1]))
                    rest.removeFirst(2)
                }
            case "L":
                var rest = numbers
                while rest.count >= 2 {
                    path.addLine(to: CGPoint(x: rest[0], y: rest[1]))
                    rest.removeFirst(2)
                }
            case "C":
                var rest = numbers
                while rest.count >= 6 {
                    path.addCurve(to: CGPoint(x: rest[4], y: rest[5]),
                                  control1: CGPoint(x: rest[0], y: rest[1]),
                                  control2: CGPoint(x: rest[2], y: rest[3]))
                    rest.removeFirst(6)
                }
            default:
                break
            }
            numbers = []
        }
        var token = ""
        func number() {
            if let n = Double(token) { numbers.append(CGFloat(n)) }
            token = ""
        }
        for ch in d {
            if ch == "M" || ch == "L" || ch == "C" {
                number()
                flush()
                command = ch
            } else if ch == " " || ch == "," {
                number()
            } else if ch == "-" && !token.isEmpty && token.last != "e" {
                number()
                token = "-"
            } else {
                token.append(ch)
            }
        }
        number()
        flush()
        return path
    }
}
