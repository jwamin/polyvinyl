import Foundation

struct TrackSpan: Identifiable {
    var id: UUID = .init()
    var startSec: Double
    var endSec: Double

    var durationSec: Double { endSec - startSec }
}

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

enum ExportFormat: String, CaseIterable, Identifiable {
    case flac, mp3, wav
    var id: String { rawValue }
    var displayName: String { rawValue.uppercased() }
    var fileExtension: String { rawValue }
}

struct RMSResult {
    let values: [Double]
    let times: [Double]
    let durationSec: Double
    let sampleRate: Int
}
