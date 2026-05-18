import Foundation
import PolyvinylDSP

enum DSPError: Error, LocalizedError {
    case analysisError(String)
    var errorDescription: String? {
        if case .analysisError(let m) = self { return m }
        return nil
    }
}

enum DSPBridge {
    static func waveformEnvelope(path: String, numBins: Int = 2048) throws -> (envelope: [Double], durationSec: Double) {
        var r = PvDspEnvResult()
        let status = pv_dsp_waveform_envelope(path, Int32(numBins), &r)
        defer { pv_dsp_free_env_result(&r) }
        guard status == 0 else {
            throw DSPError.analysisError(r.error.map { String(cString: $0) } ?? "DSP envelope error")
        }
        return (Array(UnsafeBufferPointer(start: r.envelope, count: r.n_bins)), r.duration_sec)
    }

    static func rmsWindowSeries(path: String, windowMs: Double = 60.0) throws -> RMSResult {
        var r = PvDspRmsResult()
        let status = pv_dsp_rms_window_series(path, windowMs, &r)
        defer { pv_dsp_free_rms_result(&r) }
        guard status == 0 else {
            throw DSPError.analysisError(r.error.map { String(cString: $0) } ?? "DSP RMS error")
        }
        let values = Array(UnsafeBufferPointer(start: r.rms, count: r.n))
        let times = Array(UnsafeBufferPointer(start: r.times_center, count: r.n))
        return RMSResult(values: values, times: times, durationSec: r.duration_sec, sampleRate: Int(r.sample_rate))
    }
}
