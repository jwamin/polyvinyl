import Foundation
import AVFoundation
import Observation

@MainActor
@Observable
final class AppModel {
    // Source
    var wavURL: URL?
    var wavInfo: WavFileInfo?
    var outputDirectory: URL?

    // Waveform data (from DSP analysis)
    var envelope: [Double] = []
    var rmsValues: [Double] = []
    var rmsTimes: [Double] = []
    var durationSec: Double = 0

    // Silence detection parameters
    var silenceThreshold: Double = 0.018
    var minSilenceSec: Double = 1.0
    var minSplitGapSec: Double = 30.0

    // Tracks
    var spans: [TrackSpan] = []
    var titles: [String] = []
    var selectedTrackIndex: Int?

    // MusicBrainz
    var artistQuery: String = ""
    var albumQuery: String = ""

    // Export format toggles
    var exportFlac: Bool = true
    var exportMp3: Bool = false
    var exportWav: Bool = false

    // UI state
    var isBusy: Bool = false
    var activityLog: String = ""
    var alertMessage: String = ""
    var showingAlert: Bool = false

    // Preview
    private var audioPlayer: AVAudioPlayer?
    private var previewStopTask: Task<Void, Never>?
    var isPlaying: Bool = false
    var isPaused: Bool = false

    private let mbClient: MusicBrainzClient

    var appVersion: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
    }

    var ffmpegPath: String? { AudioExporter.findFFmpeg() }

    var canPlay: Bool {
        wavURL != nil && !spans.isEmpty && selectedTrackIndex != nil && (!isPlaying || isPaused)
    }

    var cutTimes: [Double] { SilenceDetector.internalCutTimes(spans) }

    init() {
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        mbClient = MusicBrainzClient(appVersion: version)
    }

    // MARK: - File Loading

    func loadWAV(url: URL) {
        let accessing = url.startAccessingSecurityScopedResource()
        do {
            wavInfo = try WavInfoReader.read(url: url)
            if accessing { url.stopAccessingSecurityScopedResource() }
            wavURL = url
            envelope = []; rmsValues = []; rmsTimes = []
            spans = []; titles = []
            selectedTrackIndex = nil
            durationSec = wavInfo?.durationSec ?? 0
            log("Loaded \(url.lastPathComponent) — \(wavInfo?.channelDescription ?? "") @ \(wavInfo?.sampleRateHz ?? 0) Hz, \(wavInfo?.formattedDuration ?? "")")
            Task { await analyzeWaveform() }
        } catch {
            if accessing { url.stopAccessingSecurityScopedResource() }
            showAlert(error.localizedDescription)
        }
    }

    func setOutputDirectory(url: URL) {
        outputDirectory = url
        log("Output directory: \(url.path)")
    }

    // MARK: - Analysis

    func analyzeWaveform() async {
        guard let url = wavURL else { return }
        isBusy = true
        log("Analyzing waveform…")
        let path = url.path
        do {
            let (env, dur) = try await Task.detached(priority: .userInitiated) {
                try DSPBridge.waveformEnvelope(path: path)
            }.value
            let rms = try await Task.detached(priority: .userInitiated) {
                try DSPBridge.rmsWindowSeries(path: path)
            }.value
            let (sugThresh, sugMinSil) = SilenceDetector.suggestParams(rms: rms)
            envelope = env
            durationSec = dur
            rmsValues = rms.values
            rmsTimes = rms.times
            silenceThreshold = sugThresh
            minSilenceSec = sugMinSil
            log(String(format: "Analysis done. Suggested threshold %.3f, min silence %.2fs.", sugThresh, sugMinSil))
            await detectTracks()
        } catch {
            log("Analysis failed: \(error.localizedDescription)")
        }
        isBusy = false
    }

    // MARK: - Track Detection

    func detectTracks() async {
        guard !rmsValues.isEmpty else { log("No waveform data — load a WAV file first."); return }
        isBusy = true
        log("Detecting tracks…")
        let params = SilenceDetector.Parameters(
            silenceThresholdLinear: silenceThreshold,
            minSilenceSec: minSilenceSec,
            minSplitGapSec: minSplitGapSec
        )
        let snap = RMSResult(values: rmsValues, times: rmsTimes, durationSec: durationSec, sampleRate: 44100)
        let detected = await Task.detached(priority: .userInitiated) {
            SilenceDetector.detectTrackSpans(rms: snap, params: params)
        }.value
        spans = detected
        titles = (0..<detected.count).map { String(format: "Track %02d", $0 + 1) }
        selectedTrackIndex = nil
        log("Detected \(detected.count) track\(detected.count == 1 ? "" : "s").")
        isBusy = false
    }

    // MARK: - MusicBrainz

    func lookupMusicBrainz() async {
        isBusy = true
        log("Searching MusicBrainz…")
        do {
            let result = try await mbClient.lookup(
                artist: artistQuery.isEmpty ? nil : artistQuery,
                album: albumQuery.isEmpty ? nil : albumQuery
            )
            artistQuery = result.artistCredit
            albumQuery = result.releaseTitle
            titles = AudioExporter.titlesForSpanCount(mbTitles: result.trackTitles, count: spans.count)
            log("Found: \(result.artistCredit) – \(result.releaseTitle) (\(result.trackTitles.count) tracks)")
        } catch {
            log("MusicBrainz lookup failed: \(error.localizedDescription)")
        }
        isBusy = false
    }

    // MARK: - Export

    func exportTracks() async {
        guard let wavURL else { log("No WAV file loaded."); return }
        guard let outputDir = outputDirectory else { log("No output directory set."); return }
        guard !spans.isEmpty else { log("No tracks detected."); return }

#if os(macOS)
        guard let ffmpeg = ffmpegPath else {
            log("ffmpeg not found. Install via Homebrew: brew install ffmpeg")
            return
        }
        let formats = ExportFormat.allCases.filter {
            switch $0 { case .flac: exportFlac; case .mp3: exportMp3; case .wav: exportWav }
        }
        guard !formats.isEmpty else { log("Select at least one export format."); return }

        isBusy = true
        let artist = artistQuery.isEmpty ? "Unknown Artist" : artistQuery
        let album = albumQuery.isEmpty ? "Unknown Album" : albumQuery
        let albumDir = AudioExporter.albumOutputDir(base: outputDir, artist: artist, album: album)
        let path = wavURL.path
        var failed = 0

        for (i, span) in spans.enumerated() {
            let title = i < titles.count ? titles[i] : String(format: "Track %02d", i + 1)
            for fmt in formats {
                let name = AudioExporter.trackFilename(index: i + 1, title: title, format: fmt)
                let dest = albumDir.appendingPathComponent(name)
                do {
                    try await Task.detached(priority: .userInitiated) {
                        try AudioExporter.encodeSegment(
                            sourcePath: path, startSec: span.startSec, endSec: span.endSec,
                            outputPath: dest, format: fmt, ffmpegBin: ffmpeg
                        )
                    }.value
                    log("✓ \(name)")
                } catch {
                    failed += 1
                    log("✗ \(name): \(error.localizedDescription)")
                }
            }
        }
        log(failed == 0 ? "Export complete." : "Export done with \(failed) error(s).")
        isBusy = false
#else
        log("Export requires macOS (ffmpeg subprocess is not available on this platform).")
#endif
    }

    // MARK: - Preview

    func playSelectedTrack() {
        guard let url = wavURL, let idx = selectedTrackIndex, idx < spans.count else { return }
        stopPreview()
        let span = spans[idx]
        let accessing = url.startAccessingSecurityScopedResource()
        do {
            let player = try AVAudioPlayer(contentsOf: url)
            player.currentTime = span.startSec
            player.play()
            audioPlayer = player
            isPlaying = true
            isPaused = false
            let remaining = max(0, span.endSec - span.startSec)
            previewStopTask = Task { [weak self] in
                try? await Task.sleep(for: .seconds(remaining))
                await self?.stopPreview()
            }
        } catch {
            if accessing { url.stopAccessingSecurityScopedResource() }
            log("Preview error: \(error.localizedDescription)")
        }
    }

    func pausePreview() {
        audioPlayer?.pause()
        isPaused = true
    }

    func resumePreview() {
        audioPlayer?.play()
        isPaused = false
    }

    func stopPreview() {
        previewStopTask?.cancel()
        previewStopTask = nil
        audioPlayer?.stop()
        audioPlayer = nil
        isPlaying = false
        isPaused = false
    }

    // MARK: - Track Editing

    func insertCut(at t: Double) {
        spans = SilenceDetector.insertCut(spans, at: t, duration: durationSec)
        titles = AudioExporter.titlesForSpanCount(mbTitles: titles, count: spans.count)
    }

    func mergeWithNext(at index: Int) {
        spans = SilenceDetector.mergeWithNext(spans, index: index, duration: durationSec)
        titles = AudioExporter.titlesForSpanCount(mbTitles: titles, count: spans.count)
    }

    func deleteTrack(at index: Int) {
        if let sel = selectedTrackIndex, sel == index { selectedTrackIndex = nil }
        spans = SilenceDetector.deleteTrack(spans, index: index, duration: durationSec)
        titles = AudioExporter.titlesForSpanCount(mbTitles: titles, count: spans.count)
    }

    func setSpanRange(at index: Int, start: Double, end: Double) {
        spans = SilenceDetector.setSpanRange(spans, index: index, start: start, end: end, duration: durationSec)
    }

    func updateTitle(at index: Int, to title: String) {
        guard index < titles.count else { return }
        titles[index] = title
    }

    // MARK: - Helpers

    func log(_ text: String) {
        if !activityLog.isEmpty { activityLog += "\n" }
        activityLog += text
    }

    private func showAlert(_ msg: String) {
        alertMessage = msg
        showingAlert = true
        log("Error: \(msg)")
    }
}
