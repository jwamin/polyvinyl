import Foundation

// MARK: - TrackSpan
struct TrackSpan: Identifiable {
    var id: UUID = .init()
    var startSec: Double
    var endSec: Double
    var durationSec: Double { endSec - startSec }
}

// MARK: - RecordSide
struct RecordSide: Identifiable {
    var id: UUID = .init()
    var label: String

    var wavURL: URL?
    var wavInfo: WavFileInfo?

    var envelope: [Double] = []
    var rmsValues: [Double] = []
    var rmsTimes: [Double] = []
    var durationSec: Double = 0

    var spans: [TrackSpan] = []
    var titles: [String] = []
    var selectedTrackIndex: Int?

    var isLoaded: Bool { wavURL != nil }
    var trackCount: Int { spans.count }
}

// MARK: - Side Naming
enum SideNamingScheme: String, CaseIterable, Identifiable {
    case letters = "A, B, C…"
    case numbers = "1, 2, 3…"
    var id: String { rawValue }

    func label(for index: Int) -> String {
        switch self {
        case .letters: String(UnicodeScalar(65 + index)!)   // A, B, C, D, E, F
        case .numbers: String(index + 1)
        }
    }
}

// MARK: - WavFileInfo
struct WavFileInfo {
    let path: URL
    let fileSizeBytes: Int64
    let fileModifiedTimestamp: Double?
    let channels: Int
    let sampleRateHz: Int
    let sampleWidthBytes: Int
    let frameCount: Int64
    let compressionType: String
    let compressionName: String

    var durationSec: Double { Double(frameCount) / Double(sampleRateHz) }
    var bitsPerSample: Int { sampleWidthBytes * 8 }
    var pcmBitrateBps: Int { sampleRateHz * channels * bitsPerSample }

    var channelDescription: String {
        switch channels { case 1: "mono"; case 2: "stereo"; default: "\(channels) channels" }
    }

    var formattedDuration: String {
        let total = Int(durationSec)
        return String(format: "%d:%02d", total / 60, total % 60)
    }

    var formattedFileSize: String {
        ByteCountFormatter.string(fromByteCount: fileSizeBytes, countStyle: .file)
    }
}

// MARK: - ExportFormat
enum ExportFormat: String, CaseIterable, Identifiable {
    case flac, wav, aac
    var id: String { rawValue }
    var displayName: String { rawValue.uppercased() }
    var fileExtension: String {
        switch self {
        case .aac: "m4a"
        case .flac, .wav: rawValue
        }
    }
}

// MARK: - RMSResult
struct RMSResult {
    let values: [Double]
    let times: [Double]
    let durationSec: Double
    let sampleRate: Int
}
