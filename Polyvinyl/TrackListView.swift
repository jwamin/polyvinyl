import SwiftUI

struct TrackListView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ForEach(Array(model.spans.enumerated()), id: \.element.id) { i, _ in
            TrackRow(index: i)
                .listRowBackground(
                    model.selectedTrackIndex == i
                        ? Color.accentColor.opacity(0.12)
                        : Color.clear
                )
                .contentShape(Rectangle())
                .onTapGesture { model.selectedTrackIndex = i }
        }
    }
}

struct TrackRow: View {
    @Environment(AppModel.self) private var model
    let index: Int

    private var span: TrackSpan { model.spans[index] }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text("Track \(index + 1)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(width: 52, alignment: .leading)

                TextField("Title", text: Binding(
                    get: { index < model.titles.count ? model.titles[index] : "" },
                    set: { model.updateTitle(at: index, to: $0) }
                ))
                .font(.callout)

                Spacer()

                if model.spans.count > 1 {
                    if index < model.spans.count - 1 {
                        Button {
                            model.mergeWithNext(at: index)
                        } label: {
                            Image(systemName: "arrow.triangle.merge")
                        }
                        .buttonStyle(.borderless)
                        .help("Merge with next track")
                    }

                    Button {
                        model.deleteTrack(at: index)
                    } label: {
                        Image(systemName: "minus.circle")
                    }
                    .buttonStyle(.borderless)
                    .foregroundStyle(.red)
                    .help("Delete track")
                }
            }

            HStack(spacing: 20) {
                timeField(label: "Start", value: span.startSec) { v in
                    model.setSpanRange(at: index, start: v, end: span.endSec)
                }
                timeField(label: "End", value: span.endSec) { v in
                    model.setSpanRange(at: index, start: span.startSec, end: v)
                }
                Spacer()
                Text(String(format: "%.1f s", span.durationSec))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder
    private func timeField(label: String, value: Double, onChange: @escaping (Double) -> Void) -> some View {
        HStack(spacing: 4) {
            Text(label + ":")
                .font(.caption)
                .foregroundStyle(.secondary)
            TextField("", value: Binding(get: { value }, set: onChange),
                      format: .number.precision(.fractionLength(2)))
                .font(.caption.monospaced())
                .frame(width: 64)
#if os(iOS)
                .keyboardType(.decimalPad)
#endif
        }
    }
}
