import SwiftUI

struct WavInfoSheet: View {
    let info: WavFileInfo?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                if let info {
                    Section("File") {
                        LabeledContent("Name", value: info.path.lastPathComponent)
                        LabeledContent("Size", value: info.formattedFileSize)
                    }
                    Section("Format") {
                        LabeledContent("Channels", value: info.channelDescription)
                        LabeledContent("Sample Rate", value: "\(info.sampleRateHz) Hz")
                        LabeledContent("Bit Depth", value: "\(info.bitsPerSample)-bit")
                        LabeledContent("Duration", value: info.formattedDuration)
                        LabeledContent("Frames", value: info.frameCount.formatted())
                        LabeledContent("Compression", value: info.compressionName)
                        LabeledContent("PCM Bitrate", value: "\(info.pcmBitrateBps / 1000) kbps")
                    }
                } else {
                    ContentUnavailableView("No File Loaded", systemImage: "waveform")
                }
            }
#if os(macOS)
            .formStyle(.grouped)
#endif
            .navigationTitle("File Info")
#if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
#endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .frame(minWidth: 320, minHeight: 340)
    }
}
