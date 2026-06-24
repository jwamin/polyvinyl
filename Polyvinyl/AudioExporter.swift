import Foundation
import AVFoundation

enum AudioExportError: Error, LocalizedError {
    case encodingFailed(String)
    var errorDescription: String? {
        if case .encodingFailed(let m) = self { return m }
        return nil
    }
}

enum AudioExporter {
    static func encodeSegment(
        sourceURL: URL,
        startSec: Double,
        endSec: Double,
        outputPath: URL,
        format: ExportFormat
    ) throws {
        try FileManager.default.createDirectory(
            at: outputPath.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )

        let sourceFile = try AVAudioFile(forReading: sourceURL)
        let sourceFormat = sourceFile.processingFormat
        let sampleRate = sourceFormat.sampleRate
        let channels = Int(sourceFormat.channelCount)

        let settings: [String: Any]
        switch format {
        case .flac:
            settings = [
                AVFormatIDKey: kAudioFormatFLAC,
                AVSampleRateKey: sampleRate,
                AVNumberOfChannelsKey: channels,
            ]
        case .wav:
            settings = [
                AVFormatIDKey: kAudioFormatLinearPCM,
                AVSampleRateKey: sampleRate,
                AVNumberOfChannelsKey: channels,
                AVLinearPCMBitDepthKey: 16,
                AVLinearPCMIsFloatKey: false,
                AVLinearPCMIsBigEndianKey: false,
            ]
        case .aac:
            settings = [
                AVFormatIDKey: kAudioFormatMPEG4AAC,
                AVSampleRateKey: sampleRate,
                AVNumberOfChannelsKey: channels,
                AVEncoderBitRateKey: 192_000,
                AVEncoderBitRateStrategyKey: AVAudioBitRateStrategy_Variable,
            ]
        }

        let destFile = try AVAudioFile(
            forWriting: outputPath,
            settings: settings,
            commonFormat: sourceFormat.commonFormat,
            interleaved: sourceFormat.isInterleaved
        )

        let startFrame = AVAudioFramePosition(max(0, startSec) * sampleRate)
        let endFrame = min(sourceFile.length, AVAudioFramePosition(endSec * sampleRate))
        guard endFrame > startFrame else { return }
        sourceFile.framePosition = startFrame

        let bufferCapacity: AVAudioFrameCount = 32_768
        guard let buffer = AVAudioPCMBuffer(pcmFormat: sourceFormat, frameCapacity: bufferCapacity) else {
            throw AudioExportError.encodingFailed("Could not allocate audio buffer.")
        }

        var framesRemaining = endFrame - startFrame
        while framesRemaining > 0 {
            let framesToRead = AVAudioFrameCount(min(AVAudioFramePosition(bufferCapacity), framesRemaining))
            try sourceFile.read(into: buffer, frameCount: framesToRead)
            if buffer.frameLength == 0 { break }
            try destFile.write(from: buffer)
            framesRemaining -= AVAudioFramePosition(buffer.frameLength)
        }
    }

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
