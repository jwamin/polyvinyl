import SwiftUI

struct WaveformView: View {
    @Environment(AppModel.self) private var model
    @State private var popoverTime: Double?
    @State private var popoverAnchor: CGPoint = .zero

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .topLeading) {
                Canvas { ctx, size in
                    drawBackground(ctx, size)
                    if !model.rmsValues.isEmpty {
                        drawSilenceOverlays(ctx, size)
                        drawThresholdLine(ctx, size)
                    }
                    if !model.envelope.isEmpty {
                        drawEnvelope(ctx, size)
                    }
                    drawMarkers(ctx, size)
                }
                .onTapGesture(count: 2, coordinateSpace: .local) { loc in
                    guard model.durationSec > 0, geo.size.width > 0 else { return }
                    model.insertCut(at: loc.x / geo.size.width * model.durationSec)
                    popoverTime = nil
                }
                .onTapGesture(count: 1, coordinateSpace: .local) { loc in
                    guard model.durationSec > 0, geo.size.width > 0 else { return }
                    let t = loc.x / geo.size.width * model.durationSec
                    if popoverTime != nil {
                        popoverTime = nil
                    } else {
                        popoverTime = t
                        popoverAnchor = loc
                    }
                }

                if let t = popoverTime {
                    markerPopover(time: t, containerWidth: geo.size.width)
                        .offset(x: min(popoverAnchor.x + 6, geo.size.width - 180),
                                y: max(0, popoverAnchor.y - 60))
                }
            }
        }
        .frame(height: 170)
        .background(Color(red: 0.12, green: 0.13, blue: 0.15))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    // MARK: - Canvas Drawing

    private func drawBackground(_ ctx: GraphicsContext, _ size: CGSize) {
        ctx.fill(Path(CGRect(origin: .zero, size: size)),
                 with: .color(Color(red: 0.12, green: 0.13, blue: 0.15)))
    }

    private func drawSilenceOverlays(_ ctx: GraphicsContext, _ size: CGSize) {
        guard model.durationSec > 0 else { return }
        let windowSec = 0.06
        let minWin = max(1, Int(ceil(model.minSilenceSec / windowSec)))
        let rms = model.rmsValues
        let times = model.rmsTimes

        var runs: [(t0: Double, t1: Double, len: Int)] = []
        var runStart: Int? = nil
        for i in 0..<rms.count {
            if rms[i] < model.silenceThreshold {
                if runStart == nil { runStart = i }
            } else if let s = runStart {
                let st = s < times.count ? times[s] : Double(s) * windowSec
                let en = (i - 1) < times.count ? times[i - 1] : Double(i - 1) * windowSec
                runs.append((st, en, i - s))
                runStart = nil
            }
        }
        if let s = runStart {
            runs.append((s < times.count ? times[s] : Double(s) * windowSec, model.durationSec, rms.count - s))
        }

        for run in runs {
            let x1 = CGFloat(run.t0 / model.durationSec) * size.width
            let x2 = CGFloat(run.t1 / model.durationSec) * size.width
            let rect = CGRect(x: x1, y: 0, width: max(1, x2 - x1), height: size.height)
            let color: Color = run.len >= minWin
                ? Color(red: 0.25, green: 0.55, blue: 0.35, opacity: 0.35)   // gap = green
                : Color(red: 0.20, green: 0.35, blue: 0.65, opacity: 0.22)   // silence = blue
            ctx.fill(Path(rect), with: .color(color))
        }
    }

    private func drawThresholdLine(_ ctx: GraphicsContext, _ size: CGSize) {
        guard let maxRMS = model.rmsValues.max(), maxRMS > 0 else { return }
        let y = size.height * CGFloat(1.0 - model.silenceThreshold / maxRMS)
        var path = Path()
        var x: CGFloat = 0
        while x <= size.width {
            path.move(to: CGPoint(x: x, y: y))
            path.addLine(to: CGPoint(x: x + 6, y: y))
            x += 10
        }
        ctx.stroke(path, with: .color(Color(red: 0.85, green: 0.85, blue: 0.9, opacity: 0.55)), lineWidth: 1)
    }

    private func drawEnvelope(_ ctx: GraphicsContext, _ size: CGSize) {
        let env = model.envelope
        guard env.count > 1 else { return }
        var path = Path()
        path.move(to: CGPoint(x: 0, y: size.height))
        for (i, v) in env.enumerated() {
            let x = CGFloat(i) / CGFloat(env.count - 1) * size.width
            let y = size.height * (1.0 - CGFloat(v))
            path.addLine(to: CGPoint(x: x, y: y))
        }
        path.addLine(to: CGPoint(x: size.width, y: size.height))
        path.closeSubpath()
        ctx.fill(path, with: .color(Color(red: 0.42, green: 0.55, blue: 0.78, opacity: 0.88)))
    }

    private func drawMarkers(_ ctx: GraphicsContext, _ size: CGSize) {
        guard model.durationSec > 0 else { return }
        for t in model.cutTimes {
            let x = CGFloat(t / model.durationSec) * size.width
            var path = Path()
            path.move(to: CGPoint(x: x, y: 0))
            path.addLine(to: CGPoint(x: x, y: size.height))
            ctx.stroke(path, with: .color(Color(red: 0.95, green: 0.65, blue: 0.15, opacity: 0.95)), lineWidth: 2)
        }
    }

    // MARK: - Popover

    @ViewBuilder
    private func markerPopover(time t: Double, containerWidth: CGFloat) -> some View {
        let (before, after) = spansAroundTime(t)
        VStack(alignment: .leading, spacing: 4) {
            Text(String(format: "t = %.2f s", t))
                .font(.caption.monospaced())
                .foregroundStyle(.secondary)
            if let b = before {
                Text("Before: Track \(b + 1)\(titleSuffix(b))")
                    .font(.caption)
            }
            if let a = after {
                Text("After: Track \(a + 1)\(titleSuffix(a))")
                    .font(.caption)
            }
            Button("Dismiss") { popoverTime = nil }
                .font(.caption)
                .buttonStyle(.borderless)
                .padding(.top, 2)
        }
        .padding(8)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
        .shadow(radius: 4)
    }

    private func spansAroundTime(_ t: Double) -> (before: Int?, after: Int?) {
        var before: Int?
        var after: Int?
        for (i, span) in model.spans.enumerated() {
            if span.endSec <= t { before = i }
            if span.startSec <= t && t <= span.endSec { after = i }
        }
        return (before, after)
    }

    private func titleSuffix(_ i: Int) -> String {
        guard i < model.titles.count, !model.titles[i].isEmpty else { return "" }
        return ": \(model.titles[i])"
    }
}
