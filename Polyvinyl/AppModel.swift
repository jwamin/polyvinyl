import Foundation
import AVFoundation
import Observation

@MainActor
@Observable
final class AppModel {
    // MARK: - Sides
    var sides: [RecordSide] = [RecordSide(label: "A")]
    var currentSideIndex: Int = 0
    var sideNamingScheme: SideNamingScheme = .letters

    // MARK: - Global silence-detection params (shared across all sides)
    var silenceThreshold: Double = 0.018
    var minSilenceSec: Double = 1.0
    var minSplitGapSec: Double = 30.0

    // MARK: - MusicBrainz
    var artistQuery: String = ""
    var albumQuery: String = ""

    // MARK: - Export
    var outputDirectory: URL?
    var exportFlac: Bool = true
    var exportWav: Bool = false
    var exportAac: Bool = false

    // MARK: - UI state
    var isBusy: Bool = false
    var activityLog: String = ""
    var alertMessage: String = ""
    var showingAlert: Bool = false

    // MARK: - Preview
    private var audioPlayer: AVAudioPlayer?
    private var previewStopTask: Task<Void, Never>?
    private var previewScopeAccessing: Bool = false
    private var previewURL: URL?          // URL in use by the player (may differ from current side)
    var isPlaying: Bool = false
    var isPaused: Bool = false

    private let mbClient: MusicBrainzClient

    // MARK: - Current-side forwarding (views continue to use flat property names)

    var envelope: [Double]      { sides[currentSideIndex].envelope }
    var rmsValues: [Double]     { sides[currentSideIndex].rmsValues }
    var rmsTimes: [Double]      { sides[currentSideIndex].rmsTimes }
    var durationSec: Double     { sides[currentSideIndex].durationSec }
    var spans: [TrackSpan]      { sides[currentSideIndex].spans }
    var titles: [String]        { sides[currentSideIndex].titles }
    var wavURL: URL?            { sides[currentSideIndex].wavURL }
    var wavInfo: WavFileInfo?   { sides[currentSideIndex].wavInfo }
    var cutTimes: [Double]      { SilenceDetector.internalCutTimes(spans) }

    var selectedTrackIndex: Int? {
        get { sides[currentSideIndex].selectedTrackIndex }
        set { sides[currentSideIndex].selectedTrackIndex = newValue }
    }

    // MARK: - Computed

    var appVersion: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
    }
    var canPlay: Bool {
        wavURL != nil && !spans.isEmpty && selectedTrackIndex != nil && (!isPlaying || isPaused)
    }

    var totalTrackCount: Int { sides.reduce(0) { $0 + $1.spans.count } }

    // MARK: - Init

    init() {
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        mbClient = MusicBrainzClient(appVersion: version)
    }

    // MARK: - Side Management

    func addSide() {
        guard sides.count < 6 else { return }
        let label = sideNamingScheme.label(for: sides.count)
        sides.append(RecordSide(label: label))
        currentSideIndex = sides.count - 1
        log("Added side \(label).")
    }

    func removeSide(at index: Int) {
        guard sides.count > 1, index < sides.count else { return }
        let label = sides[index].label
        stopPreview()
        sides.remove(at: index)
        currentSideIndex = min(currentSideIndex, sides.count - 1)
        log("Removed side \(label).")
    }

    func renameSides() {
        for i in 0..<sides.count {
            sides[i].label = sideNamingScheme.label(for: i)
        }
    }

    // MARK: - File Loading

    func loadWAV(url: URL) {
        // Metadata-only scope — analyzeWaveform() opens its own scope.
        let accessing = url.startAccessingSecurityScopedResource()
        defer { if accessing { url.stopAccessingSecurityScopedResource() } }

        do {
            let info = try WavInfoReader.read(url: url)
            sides[currentSideIndex].wavInfo = info
            sides[currentSideIndex].durationSec = info.durationSec
        } catch {
            showAlert(error.localizedDescription)
            return
        }

        let sideLabel = sides[currentSideIndex].label
        let info = sides[currentSideIndex].wavInfo!
        sides[currentSideIndex].wavURL = url
        sides[currentSideIndex].envelope = []
        sides[currentSideIndex].rmsValues = []
        sides[currentSideIndex].rmsTimes = []
        sides[currentSideIndex].spans = []
        sides[currentSideIndex].titles = []
        sides[currentSideIndex].selectedTrackIndex = nil

        log("Side \(sideLabel): loaded \(url.lastPathComponent) — \(info.channelDescription) @ \(info.sampleRateHz) Hz, \(info.formattedDuration)")

        let idx = currentSideIndex
        Task { await analyzeWaveform(sideIndex: idx) }
    }

    func setOutputDirectory(url: URL) {
        outputDirectory = url
        log("Output directory: \(url.path)")
    }

    // MARK: - Analysis

    func analyzeWaveform(sideIndex: Int? = nil) async {
        let idx = sideIndex ?? currentSideIndex
        guard idx < sides.count, let url = sides[idx].wavURL else { return }
        isBusy = true
        log("Side \(sides[idx].label): analyzing waveform…")

        // Keep scope open for the entire async function — Task.detached inherits process-level
        // file access, so the scope must remain active while the DSP work runs.
        let accessing = url.startAccessingSecurityScopedResource()
        defer { if accessing { url.stopAccessingSecurityScopedResource() } }

        let path = url.path
        do {
            let (env, dur) = try await Task.detached(priority: .userInitiated) {
                try DSPBridge.waveformEnvelope(path: path)
            }.value
            let rms = try await Task.detached(priority: .userInitiated) {
                try DSPBridge.rmsWindowSeries(path: path)
            }.value
            guard idx < sides.count else { isBusy = false; return }
            let (sugThresh, sugMinSil) = SilenceDetector.suggestParams(rms: rms)
            sides[idx].envelope = env
            sides[idx].durationSec = dur
            sides[idx].rmsValues = rms.values
            sides[idx].rmsTimes = rms.times
            silenceThreshold = sugThresh
            minSilenceSec = sugMinSil
            log(String(format: "Side %@: analysis done. Suggested threshold %.3f, min silence %.2fs.",
                       sides[idx].label, sugThresh, sugMinSil))
            await detectTracks(sideIndex: idx)
        } catch {
            let label = idx < sides.count ? sides[idx].label : "?"
            log("Side \(label): analysis failed: \(error.localizedDescription)")
        }
        isBusy = false
    }

    // MARK: - Track Detection

    func detectTracks(sideIndex: Int? = nil) async {
        let idx = sideIndex ?? currentSideIndex
        guard idx < sides.count else { return }
        guard !sides[idx].rmsValues.isEmpty else {
            log("Side \(sides[idx].label): no waveform data — load a WAV file first.")
            return
        }
        isBusy = true
        log("Side \(sides[idx].label): detecting tracks…")
        let params = SilenceDetector.Parameters(
            silenceThresholdLinear: silenceThreshold,
            minSilenceSec: minSilenceSec,
            minSplitGapSec: minSplitGapSec
        )
        let snap = RMSResult(
            values: sides[idx].rmsValues,
            times: sides[idx].rmsTimes,
            durationSec: sides[idx].durationSec,
            sampleRate: 44100
        )
        let detected = await Task.detached(priority: .userInitiated) {
            SilenceDetector.detectTrackSpans(rms: snap, params: params)
        }.value
        guard idx < sides.count else { isBusy = false; return }
        sides[idx].spans = detected
        sides[idx].titles = (0..<detected.count).map { String(format: "Track %02d", $0 + 1) }
        sides[idx].selectedTrackIndex = nil
        log("Side \(sides[idx].label): detected \(detected.count) track\(detected.count == 1 ? "" : "s").")
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

            // When medium count matches side count, assign per-medium title lists directly.
            // Otherwise flatten and distribute across sides in order.
            if result.mediumCount == sides.count {
                for (i, mediumTitles) in result.trackTitlesByMedium.enumerated() {
                    sides[i].titles = AudioExporter.titlesForSpanCount(
                        mbTitles: mediumTitles, count: sides[i].spans.count)
                }
                log("Found: \(result.artistCredit) – \(result.releaseTitle) (\(result.mediumCount) side(s), \(result.trackTitles.count) tracks total)")
            } else {
                var offset = 0
                let allTitles = result.trackTitles
                for i in 0..<sides.count {
                    let count = sides[i].spans.count
                    let slice = Array(allTitles.dropFirst(offset).prefix(count))
                    sides[i].titles = AudioExporter.titlesForSpanCount(mbTitles: slice, count: count)
                    offset += count
                }
                log("Found: \(result.artistCredit) – \(result.releaseTitle) (\(result.mediumCount) MusicBrainz medium(s) → \(sides.count) side(s), \(result.trackTitles.count) tracks)")
            }
        } catch {
            log("MusicBrainz lookup failed: \(error.localizedDescription)")
        }
        isBusy = false
    }

    // MARK: - Export

    func exportTracks() async {
        guard let outputDir = outputDirectory else { log("No output directory set."); return }
        guard sides.contains(where: { $0.wavURL != nil && !$0.spans.isEmpty }) else {
            log("No tracks to export. Load WAV files and detect tracks first.")
            return
        }

        let formats = ExportFormat.allCases.filter {
            switch $0 { case .flac: exportFlac; case .wav: exportWav; case .aac: exportAac }
        }
        guard !formats.isEmpty else { log("Select at least one export format."); return }

        isBusy = true
        // Output dir comes from a fileImporter-granted security scope — must be active
        // for the duration of every write underneath it.
        let outputAccessing = outputDir.startAccessingSecurityScopedResource()
        defer { if outputAccessing { outputDir.stopAccessingSecurityScopedResource() } }
        let artist = artistQuery.isEmpty ? "Unknown Artist" : artistQuery
        let album = albumQuery.isEmpty ? "Unknown Album" : albumQuery
        let albumDir = AudioExporter.albumOutputDir(base: outputDir, artist: artist, album: album)

        // Track numbers are continuous across all sides in order.
        var globalTrackNumber = 1
        var failed = 0

        for side in sides {
            guard let sideURL = side.wavURL, !side.spans.isEmpty else { continue }

            // Each side's scope spans its entire export loop.
            let accessing = sideURL.startAccessingSecurityScopedResource()
            defer { if accessing { sideURL.stopAccessingSecurityScopedResource() } }

            for (i, span) in side.spans.enumerated() {
                let title = i < side.titles.count ? side.titles[i] : String(format: "Track %02d", globalTrackNumber)
                for fmt in formats {
                    let name = AudioExporter.trackFilename(index: globalTrackNumber, title: title, format: fmt)
                    let dest = albumDir.appendingPathComponent(name)
                    do {
                        try await Task.detached(priority: .userInitiated) {
                            try AudioExporter.encodeSegment(
                                sourceURL: sideURL, startSec: span.startSec, endSec: span.endSec,
                                outputPath: dest, format: fmt
                            )
                        }.value
                        log("✓ Side \(side.label) – \(name)")
                    } catch {
                        failed += 1
                        log("✗ Side \(side.label) – \(name): \(error.localizedDescription)")
                    }
                }
                globalTrackNumber += 1
            }
        }
        log(failed == 0 ? "Export complete." : "Export done with \(failed) error(s).")
        isBusy = false
    }

    // MARK: - Preview

    func playSelectedTrack() {
        guard let url = wavURL, let idx = selectedTrackIndex, idx < spans.count else { return }
        stopPreview()
        let span = spans[idx]

        // Keep scope open for the lifetime of the player — AVAudioPlayer may read lazily.
        let accessing = url.startAccessingSecurityScopedResource()
        do {
            let player = try AVAudioPlayer(contentsOf: url)
            previewScopeAccessing = accessing
            previewURL = url
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
        // Release using the URL captured at preview start, not the current side's URL.
        if previewScopeAccessing, let url = previewURL {
            url.stopAccessingSecurityScopedResource()
            previewScopeAccessing = false
        }
        previewURL = nil
    }

    // MARK: - Track Editing (all operate on current side)

    func insertCut(at t: Double) {
        sides[currentSideIndex].spans = SilenceDetector.insertCut(spans, at: t, duration: durationSec)
        sides[currentSideIndex].titles = AudioExporter.titlesForSpanCount(mbTitles: titles, count: spans.count)
    }

    func mergeWithNext(at index: Int) {
        sides[currentSideIndex].spans = SilenceDetector.mergeWithNext(spans, index: index, duration: durationSec)
        sides[currentSideIndex].titles = AudioExporter.titlesForSpanCount(mbTitles: titles, count: spans.count)
    }

    func deleteTrack(at index: Int) {
        if let sel = selectedTrackIndex, sel == index { selectedTrackIndex = nil }
        sides[currentSideIndex].spans = SilenceDetector.deleteTrack(spans, index: index, duration: durationSec)
        sides[currentSideIndex].titles = AudioExporter.titlesForSpanCount(mbTitles: titles, count: spans.count)
    }

    func setSpanRange(at index: Int, start: Double, end: Double) {
        sides[currentSideIndex].spans = SilenceDetector.setSpanRange(
            spans, index: index, start: start, end: end, duration: durationSec)
    }

    func updateTitle(at index: Int, to title: String) {
        guard index < sides[currentSideIndex].titles.count else { return }
        sides[currentSideIndex].titles[index] = title
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
