import Foundation

enum SilenceDetector {
    struct Parameters {
        var silenceThresholdLinear: Double = 0.018
        var minSilenceSec: Double = 1.35
        var minSplitGapSec: Double = 30.0
        var windowMs: Double = 60.0
        var boundaryPadSec: Double = 0.05
    }

    static func detectTrackSpans(rms: RMSResult, params: Parameters) -> [TrackSpan] {
        let windowSec = params.windowMs / 1000.0
        let minWindows = max(1, Int(ceil(params.minSilenceSec / windowSec)))

        // Collect silence runs
        var runs: [(start: Int, end: Int)] = []
        var runStart: Int? = nil
        for i in 0..<rms.values.count {
            if rms.values[i] < params.silenceThresholdLinear {
                if runStart == nil { runStart = i }
            } else if let s = runStart {
                runs.append((s, i - 1))
                runStart = nil
            }
        }
        if let s = runStart { runs.append((s, rms.values.count - 1)) }

        // Midpoints of long-enough runs become cut candidates
        var candidates: [Double] = []
        for run in runs where (run.end - run.start + 1) >= minWindows {
            let mid = run.start + (run.end - run.start) / 2
            candidates.append(mid < rms.times.count ? rms.times[mid] : Double(mid) * windowSec)
        }

        // Enforce minimum gap between cuts
        var cuts: [Double] = []
        for c in candidates {
            if let last = cuts.last, c - last < params.minSplitGapSec { continue }
            cuts.append(c)
        }

        // Pad back from silence midpoint
        let padded = cuts.map { max(0, $0 - params.boundaryPadSec) }

        // Build spans
        var spans: [TrackSpan] = []
        var prev = 0.0
        for cut in padded where cut > 0.01 && cut < rms.durationSec - 0.01 {
            spans.append(TrackSpan(startSec: prev, endSec: cut))
            prev = cut
        }
        spans.append(TrackSpan(startSec: prev, endSec: rms.durationSec))
        return normalize(spans, duration: rms.durationSec)
    }

    static func suggestParams(rms: RMSResult, windowSec: Double = 0.06) -> (threshold: Double, minSilenceSec: Double) {
        guard !rms.values.isEmpty else { return (0.018, 1.0) }
        let sorted = rms.values.sorted()
        let p10 = sorted[max(0, Int(Double(sorted.count) * 0.10))]
        let p50 = sorted[Int(Double(sorted.count) * 0.50)]
        let threshold = max(0.004, min(0.15, (p10 + p50) / 4.0))
        let silentSec = Double(rms.values.filter { $0 < threshold }.count) * windowSec
        return (threshold, max(0.5, min(5.0, silentSec / 20.0)))
    }

    static func normalize(_ spans: [TrackSpan], duration: Double, minSec: Double = 0.05) -> [TrackSpan] {
        var s = spans.filter { $0.durationSec >= minSec }.sorted { $0.startSec < $1.startSec }
        guard !s.isEmpty else { return [TrackSpan(startSec: 0, endSec: duration)] }
        s[0].startSec = 0
        s[s.count - 1].endSec = duration
        for i in 1..<s.count { s[i].startSec = s[i-1].endSec }
        return s.filter { $0.durationSec >= minSec }
    }

    static func internalCutTimes(_ spans: [TrackSpan]) -> [Double] {
        guard spans.count > 1 else { return [] }
        return spans.dropLast().map { $0.endSec }
    }

    static func insertCut(_ spans: [TrackSpan], at t: Double, duration: Double) -> [TrackSpan] {
        var s = spans
        guard let idx = s.firstIndex(where: { t > $0.startSec && t < $0.endSec }) else { return spans }
        let orig = s[idx]
        s[idx] = TrackSpan(startSec: orig.startSec, endSec: t)
        s.insert(TrackSpan(startSec: t, endSec: orig.endSec), at: idx + 1)
        return normalize(s, duration: duration)
    }

    static func mergeWithNext(_ spans: [TrackSpan], index: Int, duration: Double) -> [TrackSpan] {
        guard index < spans.count - 1 else { return spans }
        var s = spans
        s[index].endSec = s[index + 1].endSec
        s.remove(at: index + 1)
        return normalize(s, duration: duration)
    }

    static func deleteTrack(_ spans: [TrackSpan], index: Int, duration: Double) -> [TrackSpan] {
        guard spans.count > 1 else { return spans }
        var s = spans
        if index < s.count - 1 { s[index + 1].startSec = s[index].startSec }
        else { s[index - 1].endSec = s[index].endSec }
        s.remove(at: index)
        return normalize(s, duration: duration)
    }

    static func setSpanRange(_ spans: [TrackSpan], index: Int, start: Double, end: Double, duration: Double) -> [TrackSpan] {
        guard index < spans.count else { return spans }
        var s = spans
        s[index].startSec = start
        s[index].endSec = end
        if index > 0 { s[index - 1].endSec = start }
        if index < s.count - 1 { s[index + 1].startSec = end }
        return normalize(s, duration: duration)
    }
}
