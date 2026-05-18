import Foundation

enum AudioExportError: Error, LocalizedError {
    case ffmpegNotFound
    case encodingFailed(String)
    var errorDescription: String? {
        switch self {
        case .ffmpegNotFound: "ffmpeg not found. Install via Homebrew: brew install ffmpeg"
        case .encodingFailed(let m): m
        }
    }
}

enum AudioExporter {
    static func findFFmpeg() -> String? {
        let extraDirs = ["/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/usr/local/opt/ffmpeg/bin"]
        let pathDirs = (ProcessInfo.processInfo.environment["PATH"] ?? "").components(separatedBy: ":")
        return (pathDirs + extraDirs)
            .map { ($0 as NSString).appendingPathComponent("ffmpeg") }
            .first { FileManager.default.isExecutableFile(atPath: $0) }
    }

#if os(macOS)
    static func encodeSegment(
        sourcePath: String,
        startSec: Double,
        endSec: Double,
        outputPath: URL,
        format: ExportFormat,
        ffmpegBin: String
    ) throws {
        try FileManager.default.createDirectory(
            at: outputPath.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        let codecArgs: [String]
        switch format {
        case .flac: codecArgs = ["-c:a", "flac", "-compression_level", "8"]
        case .mp3:  codecArgs = ["-c:a", "libmp3lame", "-q:a", "2"]
        case .wav:  codecArgs = ["-c:a", "pcm_s16le"]
        }
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: ffmpegBin)
        proc.arguments = ["-y", "-ss", String(startSec), "-to", String(endSec),
                          "-i", sourcePath] + codecArgs + [outputPath.path]
        proc.standardOutput = Pipe()
        let errPipe = Pipe()
        proc.standardError = errPipe
        try proc.run()
        proc.waitUntilExit()
        if proc.terminationStatus != 0 {
            let msg = String(data: errPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? "Unknown ffmpeg error"
            throw AudioExportError.encodingFailed(msg)
        }
    }
#endif

    static func sanitize(_ name: String, maxLength: Int = 120) -> String {
        let invalid = CharacterSet(charactersIn: "/\\:*?\"<>|\0")
        var s = name.components(separatedBy: invalid).joined(separator: "_")
        while s.contains("  ") { s = s.replacingOccurrences(of: "  ", with: " ") }
        return String(s.prefix(maxLength)).trimmingCharacters(in: .whitespaces)
    }

    static func albumOutputDir(base: URL, artist: String, album: String) -> URL {
        base.appendingPathComponent(sanitize(artist)).appendingPathComponent(sanitize(album))
    }

    static func trackFilename(index: Int, title: String, format: ExportFormat) -> String {
        String(format: "%02d \u{2013} %@.%@", index, sanitize(title), format.fileExtension)
    }

    static func titlesForSpanCount(mbTitles: [String], count: Int) -> [String] {
        (0..<count).map { i in i < mbTitles.count ? mbTitles[i] : String(format: "Track %02d", i + 1) }
    }
}
