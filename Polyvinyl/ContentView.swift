import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @State private var model = AppModel()
    @State private var showingWavPicker = false
    @State private var showingOutputPicker = false
    @State private var showingWavInfo = false

    var body: some View {
        NavigationStack {
            Form {
                sourceSection
                silenceSection
                waveformSection
                trackSection
                musicBrainzSection
                outputSection
                logSection
            }
#if os(macOS)
            .formStyle(.grouped)
#endif
            .navigationTitle("Polyvinyl")
            .toolbar {
#if os(macOS)
                ToolbarItem(placement: .navigation) {
                    Label("Vinyl rip splitter", systemImage: "opticaldisc")
                        .labelStyle(.iconOnly)
                        .help("Vinyl / optical media rip splitter")
                }
#endif
                ToolbarItem(placement: .primaryAction) {
                    if model.isBusy {
                        ProgressView()
                            .controlSize(.small)
                            .transition(.opacity)
                    }
                }
            }
        }
        .environment(model)
        .fileImporter(
            isPresented: $showingWavPicker,
            allowedContentTypes: [UTType.audio, UTType(mimeType: "audio/wav") ?? .audio],
            allowsMultipleSelection: false
        ) { result in
            if case .success(let urls) = result, let url = urls.first {
                model.loadWAV(url: url)
            }
        }
        .fileImporter(
            isPresented: $showingOutputPicker,
            allowedContentTypes: [.folder],
            allowsMultipleSelection: false
        ) { result in
            if case .success(let urls) = result, let url = urls.first {
                model.setOutputDirectory(url: url)
            }
        }
        .sheet(isPresented: $showingWavInfo) {
            WavInfoSheet(info: model.wavInfo)
        }
        .alert(model.alertMessage, isPresented: $model.showingAlert) {
            Button("OK", role: .cancel) {}
        }
    }

    // MARK: - Source

    @ViewBuilder
    private var sourceSection: some View {
        Section("Source") {
            HStack {
                Button("Open WAV…") { showingWavPicker = true }
                Spacer()
                if let info = model.wavInfo {
                    Text(info.path.lastPathComponent)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Button {
                        showingWavInfo = true
                    } label: {
                        Image(systemName: "info.circle")
                    }
                    .buttonStyle(.borderless)
                    .help("Show file details")
                }
            }
        }
    }

    // MARK: - Silence Detection

    @ViewBuilder
    private var silenceSection: some View {
        @Bindable var m = model
        Section {
            LabeledContent("Threshold") {
                HStack {
                    Slider(value: $m.silenceThreshold, in: 0.004...0.15)
                    Text(String(format: "%.3f", model.silenceThreshold))
                        .monospacedDigit()
                        .frame(width: 48, alignment: .trailing)
                }
            }
            .help("Energy below this fraction of full scale counts as silence")

            LabeledContent("Min. silence (s)") {
                HStack {
                    Slider(value: $m.minSilenceSec, in: 0.05...5.0)
                    Text(String(format: "%.2f", model.minSilenceSec))
                        .monospacedDigit()
                        .frame(width: 48, alignment: .trailing)
                }
            }
            .help("Seconds of quiet required to mark a track boundary")

            LabeledContent("Min. gap (s)") {
                HStack {
                    Slider(value: $m.minSplitGapSec, in: 5...600)
                    Text(String(format: "%.0f", model.minSplitGapSec))
                        .monospacedDigit()
                        .frame(width: 48, alignment: .trailing)
                }
            }
            .help("Minimum distance between cuts")

            HStack {
                Button("Analyse") {
                    Task { await model.analyzeWaveform() }
                }
                .disabled(model.wavURL == nil || model.isBusy)

                Spacer()

                Button("Refresh Markers") {
                    Task { await model.detectTracks() }
                }
                .disabled(model.rmsValues.isEmpty || model.isBusy)
            }
        } header: {
            Text("Silence Detection")
        }
    }

    // MARK: - Waveform

    @ViewBuilder
    private var waveformSection: some View {
        Section {
            WaveformView()
                .listRowInsets(EdgeInsets())
        } header: {
            Text("Waveform")
        } footer: {
            Text("Double-tap to insert a cut · Tap anywhere for marker info")
                .font(.caption)
        }
    }

    // MARK: - Track List

    @ViewBuilder
    private var trackSection: some View {
        Section("Tracks") {
            if model.spans.isEmpty {
                ContentUnavailableView {
                    Label("No Tracks Detected", systemImage: "waveform.slash")
                } description: {
                    Text("Open a WAV file and tap Analyse to detect track boundaries.")
                }
                .listRowBackground(Color.clear)
            } else {
                TrackListView()
                previewRow
            }
        }
    }

    @ViewBuilder
    private var previewRow: some View {
        HStack(spacing: 16) {
            Button {
                model.isPaused ? model.resumePreview() : model.playSelectedTrack()
            } label: {
                Image(systemName: model.isPaused ? "play.circle.fill" : "play.fill")
            }
            .disabled(!model.canPlay)

            Button { model.pausePreview() } label: {
                Image(systemName: "pause.fill")
            }
            .disabled(!model.isPlaying || model.isPaused)

            Button { model.stopPreview() } label: {
                Image(systemName: "stop.fill")
            }
            .disabled(!model.isPlaying && !model.isPaused)

            Spacer()

            if model.selectedTrackIndex == nil {
                Text("Select a track to preview")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .buttonStyle(.borderless)
    }

    // MARK: - MusicBrainz

    @ViewBuilder
    private var musicBrainzSection: some View {
        @Bindable var m = model
        Section("MusicBrainz") {
            TextField("Artist", text: $m.artistQuery)
            TextField("Album / Release", text: $m.albumQuery)
            Button("Look Up") {
                Task { await model.lookupMusicBrainz() }
            }
            .disabled((model.artistQuery.isEmpty && model.albumQuery.isEmpty) || model.isBusy)
        }
    }

    // MARK: - Output

    @ViewBuilder
    private var outputSection: some View {
        @Bindable var m = model
        Section("Output") {
            Toggle("FLAC (lossless)", isOn: $m.exportFlac)
            Toggle("MP3 (VBR ~190 kbps)", isOn: $m.exportMp3)
            Toggle("WAV (PCM 16-bit)", isOn: $m.exportWav)

            HStack {
                Button("Choose Folder…") { showingOutputPicker = true }
                Spacer()
                if let dir = model.outputDirectory {
                    Text(dir.lastPathComponent)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }

#if os(macOS)
            if model.ffmpegPath == nil {
                Label("ffmpeg not found — install via Homebrew to enable export", systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
#endif

            Button {
                Task { await model.exportTracks() }
            } label: {
                Label("Export Tracks", systemImage: "square.and.arrow.down")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(model.spans.isEmpty || model.outputDirectory == nil || model.isBusy
                      || (!model.exportFlac && !model.exportMp3 && !model.exportWav))
        }
    }

    // MARK: - Activity Log

    @ViewBuilder
    private var logSection: some View {
        Section("Activity Log") {
            ScrollView(.vertical) {
                Text(model.activityLog.isEmpty ? "No activity yet." : model.activityLog)
                    .font(.caption.monospaced())
                    .foregroundStyle(model.activityLog.isEmpty ? .tertiary : .primary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
                    .padding(.vertical, 4)
            }
            .frame(minHeight: 120)
        }
    }
}

#Preview {
    ContentView()
}
