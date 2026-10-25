import ImageIO
import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

/// A file on its way to the tablet's library, waiting to be confirmed.
struct Chosen: Identifiable {
    let id = UUID()
    let data: Data
    let type: UTType
    let fileName: String
    var name: String

    var isImage: Bool { type.conforms(to: .image) }
}

/// What the server will take, and the same ceiling it enforces. Checked here
/// too so a 200MB video is refused now rather than after it has uploaded.
enum Library {
    static let types: [UTType] = [.pdf, .epub, .image]
    static let maxBytes = 64 << 20

    static func size(_ bytes: Int) -> String {
        ByteCountFormatter.string(fromByteCount: Int64(bytes), countStyle: .file)
    }

    static func read(_ url: URL) throws -> Chosen {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        let bytes = (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
        if bytes > maxBytes {
            throw ServerError.said("The tablet takes up to 64 MB; this is \(size(bytes)).")
        }
        let data = try Data(contentsOf: url)
        let type = UTType(filenameExtension: url.pathExtension) ?? .data
        return try chosen(data, type: type, fileName: url.lastPathComponent)
    }

    /// The one way in, for a file, a photo from the library or the camera.
    static func chosen(_ data: Data, type: UTType, fileName: String) throws -> Chosen {
        guard types.contains(where: type.conforms) else {
            throw ServerError.said("It takes a pdf, an epub or an image.")
        }
        var (data, type, fileName) = (data, type, fileName)
        if type.conforms(to: .image), !pillowReads.contains(where: type.conforms) {
            guard let jpeg = jpeg(data) else {
                throw ServerError.said("That picture could not be turned into a jpeg.")
            }
            data = jpeg
            type = .jpeg
            fileName = (fileName as NSString).deletingPathExtension + ".jpg"
        }
        if data.count > maxBytes {
            throw ServerError.said("The tablet takes up to 64 MB; this is \(size(data.count)).")
        }
        let name = (fileName as NSString).deletingPathExtension.trimmingCharacters(in: .whitespaces)
        return Chosen(data: data, type: type, fileName: fileName, name: name.isEmpty ? "Untitled" : name)
    }

    /// What the server's Pillow opens without plugins. A phone's own format,
    /// HEIC, is not among them, so anything else is made a jpeg here.
    private static let pillowReads: [UTType] = [.png, .jpeg, .gif, .webP, .bmp, .tiff]

    /// Re-encoded with its metadata, the rotation flag included: the server
    /// turns the picture the way the camera meant it.
    private static func jpeg(_ data: Data) -> Data? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
        let out = NSMutableData()
        guard let dest = CGImageDestinationCreateWithData(out, UTType.jpeg.identifier as CFString, 1, nil) else {
            return nil
        }
        let options = [kCGImageDestinationLossyCompressionQuality: 0.9] as CFDictionary
        CGImageDestinationAddImageFromSource(dest, source, 0, options)
        return CGImageDestinationFinalize(dest) ? out as Data : nil
    }

    /// A photo has no file name of its own here, so it is named for when it
    /// was chosen.
    static func photoName() -> String {
        "Photo " + Date.now.formatted(.dateTime.day().month(.abbreviated).hour().minute())
    }
}

/// Put a file in the tablet's library, as a real document. Not drawn: the
/// pen can only trace a picture, and xochitl renders a pdf itself far
/// better than a tracing of it. It asks first, every time, because the way
/// in is a restart of xochitl.
///
/// Three ways to choose it: a file, a photo from the library, or, on the
/// iPhone, the camera. Whatever is chosen is held in memory only; a photo
/// taken here is never saved to the library.
struct SendToTabletButton: View {
    @State private var picking = false
    @State private var browsing = false
    @State private var photo: PhotosPickerItem?
    @State private var shooting = false
    @State private var shot: Data?
    @Environment(Toasts.self) private var toasts
    @Environment(Outbox.self) private var outbox

    var body: some View {
        Menu {
            Button { browsing = true } label: { Label("Photo library", systemImage: "photo.on.rectangle") }
            #if os(iOS)
            if UIImagePickerController.isSourceTypeAvailable(.camera) {
                Button { shooting = true } label: { Label("Take a photo", systemImage: "camera") }
            }
            #endif
            Button { picking = true } label: { Label("Files", systemImage: "folder") }
        } label: {
            Image(systemName: "doc.badge.arrow.up")
        }
        .help("Put a pdf, an epub or an image on the tablet")
        .accessibilityLabel("Put a document on the tablet")
        .fileImporter(isPresented: $picking, allowedContentTypes: Library.types) { result in
            switch result {
            case let .success(url):
                do { outbox.chosen = try Library.read(url) } catch {
                    toasts.failure("That file will not go", error.localizedDescription)
                }
            case let .failure(error):
                toasts.failure("Could not open it", error.localizedDescription)
            }
        }
        .photosPicker(isPresented: $browsing, selection: $photo, matching: .images, preferredItemEncoding: .current)
        .onChange(of: photo) { _, item in
            guard let item else { return }
            photo = nil
            Task { await take(item) }
        }
        #if os(iOS)
        // The confirmation is a sheet of its own, which cannot open until
        // the camera has gone, so the photo waits for the dismissal.
        .fullScreenCover(isPresented: $shooting) {
            if let data = shot { shot = nil; choose(data, type: .jpeg) }
        } content: {
            Camera { shot = $0?.jpegData(compressionQuality: 0.9) }
                .ignoresSafeArea()
        }
        #endif
    }

    /// The photo as it is stored, a HEIC from an iPhone's camera, which
    /// `Library.chosen` turns into a jpeg.
    private func take(_ item: PhotosPickerItem) async {
        do {
            guard let data = try await item.loadTransferable(type: Data.self) else {
                toasts.failure("Could not open it", "The photo came back empty.")
                return
            }
            let type = item.supportedContentTypes.first { $0.conforms(to: .image) } ?? .jpeg
            choose(data, type: type)
        } catch {
            toasts.failure("Could not open it", error.localizedDescription)
        }
    }

    private func choose(_ data: Data, type: UTType) {
        let fileName = Library.photoName() + "." + (type.preferredFilenameExtension ?? "jpg")
        do { outbox.chosen = try Library.chosen(data, type: type, fileName: fileName) } catch {
            toasts.failure("That photo will not go", error.localizedDescription)
        }
    }
}

#if os(iOS)
/// The system camera. SwiftUI has no camera of its own, so this is
/// UIKit's picker, which hands back the picture and is dismissed.
private struct Camera: UIViewControllerRepresentable {
    let took: (UIImage?) -> Void
    @Environment(\.dismiss) private var dismiss

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_: UIImagePickerController, context _: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let camera: Camera
        init(_ camera: Camera) { self.camera = camera }

        func imagePickerController(_: UIImagePickerController,
                                   didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            camera.took(info[.originalImage] as? UIImage)
            camera.dismiss()
        }

        func imagePickerControllerDidCancel(_: UIImagePickerController) {
            camera.dismiss()
        }
    }
}
#endif

/// The one file waiting to go, shared by the button, the drop target and
/// both pages.
@Observable
final class Outbox {
    var chosen: Chosen?
}

/// The confirmation, and the drop target: a file can be dropped anywhere
/// on the window.
struct LibraryDrop: ViewModifier {
    @Environment(Outbox.self) private var outbox
    @Environment(Toasts.self) private var toasts
    @State private var dragging = false

    func body(content: Content) -> some View {
        @Bindable var outbox = outbox
        content
            .dropDestination(for: URL.self) { urls, _ in
                guard let url = urls.first else { return false }
                do { outbox.chosen = try Library.read(url) } catch {
                    toasts.failure("That file will not go", error.localizedDescription)
                }
                return true
            } isTargeted: { dragging = $0 }
            .overlay {
                if dragging {
                    RoundedRectangle(cornerRadius: 16)
                        .strokeBorder(style: StrokeStyle(lineWidth: 2, dash: [8, 6]))
                        .foregroundStyle(.secondary)
                        .background(.regularMaterial, in: .rect(cornerRadius: 16))
                        .overlay { Text("Drop it to put it on the tablet").foregroundStyle(.secondary) }
                        .padding(16)
                        .allowsHitTesting(false)
                }
            }
            .sheet(item: $outbox.chosen) { chosen in
                ConfirmLibrary(chosen: chosen)
            }
    }
}

extension View {
    func libraryDrop() -> some View { modifier(LibraryDrop()) }
}

private struct ConfirmLibrary: View {
    @State var chosen: Chosen
    @State private var sending = false
    @Environment(Connection.self) private var connection
    @Environment(Toasts.self) private var toasts
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Put this on the tablet?").font(.title3.weight(.semibold))
            HStack(alignment: .top, spacing: 12) {
                Group {
                    if chosen.isImage, let image = PlatformImage(data: chosen.data) {
                        Image(platform: image).resizable().scaledToFit()
                    } else {
                        Image(systemName: "doc.text").font(.title).foregroundStyle(.secondary)
                    }
                }
                .frame(width: 80, height: 80)
                .background(.background.secondary, in: .rect(cornerRadius: 6))
                VStack(alignment: .leading, spacing: 6) {
                    Text("Name in the library").font(.caption).foregroundStyle(.secondary)
                    TextField("Name", text: $chosen.name)
                        .textFieldStyle(.roundedBorder)
                        .disabled(sending)
                        .onSubmit(send)
                    Text("\(chosen.fileName) · \(Library.size(chosen.data.count))")
                        .font(.caption).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                }
            }
            Text("It becomes a document in the library, rendered by the tablet itself\(chosen.isImage ? " as a one-page pdf in greys" : ""). To take it in, the tablet's interface restarts: whatever is open closes and the screen reloads for about ten seconds. Then open it from the library.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            HStack {
                Spacer()
                Button("Not now") { dismiss() }.disabled(sending)
                Button(action: send) {
                    Text(sending ? "Restarting the tablet…" : "Put it on the tablet")
                }
                .buttonStyle(.borderedProminent)
                .disabled(sending)
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(24)
        .frame(minWidth: 360, idealWidth: 460)
        .interactiveDismissDisabled(sending)
        .presentationDetents([.medium])
    }

    private func send() {
        guard !sending, let server = connection.server else { return }
        sending = true
        let name = chosen.name.trimmingCharacters(in: .whitespaces)
        Task {
            do {
                let said = try await API.library(
                    server, file: chosen.data,
                    type: chosen.type.preferredMIMEType ?? "application/octet-stream",
                    name: name.isEmpty ? "Untitled" : name)
                toasts.success("“\(said.name)” is in the library", "Open it on the tablet once the screen has come back.")
                dismiss()
            } catch {
                toasts.failure("It did not reach the tablet", error.localizedDescription)
            }
            sending = false
        }
    }
}
