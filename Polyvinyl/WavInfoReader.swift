import Foundation
import AVFoundation

enum WavInfoReaderError: Error, LocalizedError {
    case cannotOpen(String)
    var errorDescription: String? {
        if case .cannotOpen(let m) = self { return m }
        return nil
    }
}

enum WavInfoReader {
    static func read(url: URL) throws -> WavFileInfo {
        let attrs = try FileManager.default.attributesOfItem(atPath: url.path)
        let fileSize = attrs[.size] as? Int64 ?? 0
        let modTime = (attrs[.modificationDate] as? Date)?.timeIntervalSince1970

        do {
            let file = try AVAudioFile(forReading: url)
            let desc = file.fileFormat.streamDescription.pointee
            let isPCM = desc.mFormatID == kAudioFormatLinearPCM
            let bitsPerChannel = desc.mBitsPerChannel > 0 ? Int(desc.mBitsPerChannel) : 16
            return WavFileInfo(
                path: url,
                fileSizeBytes: fileSize,
                fileModifiedTimestamp: modTime,
                channels: Int(desc.mChannelsPerFrame),
                sampleRateHz: Int(desc.mSampleRate),
                sampleWidthBytes: bitsPerChannel / 8,
                frameCount: file.length,
                compressionType: isPCM ? "NONE" : "OTHER",
                compressionName: isPCM ? "not compressed" : "compressed"
            )
        } catch {
            throw WavInfoReaderError.cannotOpen(error.localizedDescription)
        }
    }
}
