//  HistogramPlot.swift — the histogram as it is drawn, in either style.
//
//  Kept apart from the panel (sessions, folding, menus) so a check can render it from synthetic counts.
//  Split out of HistogramPanel.swift (upstream 2.3.0's RFC-051 rework) with `HistogramStyle` and
//  `HistogramDisplay` moved along with it — but **without the HDR span**: this build does not take HDR,
//  so the plot is the SDR histogram alone, as it was.
//
//  What differs on the Mac: the plot's words are in the theme's type (`Theme.Font.ui`), as every other
//  word in the column is, not a bare system size.

import SwiftUI

/// How the histogram is drawn. RFC-051: the panel is Capture One style only and the ⋯ menu is gone; the
/// other style stays drawable (with no title to show), so a check may still draw it.
enum HistogramStyle: String, CaseIterable, Identifiable, Sendable {
    case captureOne = "captureOne", spektraLab = "spektraLab"
    var id: String { rawValue }
}

/// The histogram plot, in either style: Capture One's lines over the luminance, or the Latitude card's
/// filled grey shape.
struct HistogramPlot: View {
    let h: Layer2Histogram?
    let style: HistogramStyle

    var body: some View {
        let shown = h.map { HistogramDisplay($0) }
        return Canvas { ctx, size in draw(ctx, size, shown: shown) }
            .accessibilityLabel(L("Histogram"))
    }

    private func draw(_ ctx: GraphicsContext, _ size: CGSize, shown: HistogramDisplay?) {
        let lines = style == .captureOne
        if lines {
            var grid = Path()
            for k in 1..<4 {
                let x = size.width * CGFloat(k) / 4
                grid.move(to: CGPoint(x: x, y: 0)); grid.addLine(to: CGPoint(x: x, y: size.height))
            }
            for k in 1..<3 {
                let y = size.height * CGFloat(k) / 3
                grid.move(to: CGPoint(x: 0, y: y)); grid.addLine(to: CGPoint(x: size.width, y: y))
            }
            ctx.stroke(grid, with: .color(Theme.rule), lineWidth: 0.5)
        }
        if let shown {
            if lines {
                ctx.fill(Self.shape(shown[.luma], size, closed: true), with: .color(Theme.dim.opacity(0.55)))
                let channels: [(Layer2Histogram.Channel, CurveChannel)] = [(.red, .red), (.green, .green), (.blue, .blue)]
                for (channel, swatch) in channels {
                    ctx.stroke(Self.shape(shown[channel], size, closed: false), with: .color(swatch.swatch.opacity(0.9)),
                               style: StrokeStyle(lineWidth: 1.1, lineJoin: .round))
                }
            } else {
                ctx.fill(Self.shape(shown[.luma], size, closed: true), with: .color(Theme.latitudeInside))
            }
        }
        ctx.fill(Path(CGRect(x: 0, y: size.height - (lines ? 0.5 : 1), width: size.width, height: lines ? 0.5 : 1)),
                 with: .color(Theme.rule))
    }

    /// The bins, 0…1, across the plot: the shape closed onto the base, or the line alone. The plot's
    /// top 2 pt are left clear, as the Latitude card leaves them.
    static func shape(_ bins: [Float], _ size: CGSize, closed: Bool) -> Path {
        var p = Path()
        guard bins.count > 1 else { return p }
        let top: CGFloat = 2, base = size.height
        func point(_ i: Int) -> CGPoint {
            CGPoint(x: size.width * CGFloat(i) / CGFloat(bins.count - 1), y: base - CGFloat(bins[i]) * (base - top))
        }
        if closed { p.move(to: CGPoint(x: 0, y: base)); p.addLine(to: point(0)) } else { p.move(to: point(0)) }
        for i in 1..<bins.count { p.addLine(to: point(i)) }
        if closed { p.addLine(to: CGPoint(x: size.width, y: base)); p.closeSubpath() }
        return p
    }
}

/// The histogram as it is drawn: Capture One's way of showing it, not the counts over the tallest bin.
///
/// The owner, 2026-10-24, holding the same frame (`_DSC4680.NEF`) in both: the bins sat where Capture
/// One's do, peak for peak, and were flat. Two things flattened them, both in the drawing and neither
/// in the counts (`Layer2Histogram`, which the curve's own readings keep as they are):
///
/// - **One spike set the scale.** The counts were over the tallest bin of all four channels, and on
///   that frame the tallest was a narrow red spike near black, three times the luminance's body: every
///   other line lay in the plot's lowest third. The scale is now the tallest of each channel smoothed
///   wide (σ 6 bins), which a spike a few bins wide is diluted by and a body is not, with a tenth of
///   headroom; a spike runs off the top, as Capture One lets it.
/// - **Linear heights hide the tones that matter.** Capture One's secondary humps stand about a
///   quarter as tall as its peak where the counts are 1/25 of it: its heights are compressed. A square
///   root gives the same reading (measured on a capture of the develop page, 2026-10-24: the peak at the
///   top with two to seven bins clipped, the mid-tones at 0.15–0.35 of the plot where they were 0.02).
///
/// The lines are smoothed a little (σ 1.2 bins), as Capture One's are; the two bins at each end, the
/// clipped black and white, are left out as they were.
struct HistogramDisplay {
    private let rows: [[Float]]
    /// The count a full-height line stands for (squared).
    let top: Float

    init(_ h: Layer2Histogram) {
        let channels = Layer2Histogram.Channel.allCases
        self.init(counts: channels.map { c in
            Array(h.counts[(c.rawValue * 256)..<(c.rawValue * 256 + 256)]).map { Float($0) }   // not `Float.init`: on a UInt32 that is `init(bitPattern:)`
        }, clipsWhite: true)
    }

    /// Counts a channel, in `Layer2Histogram.Channel` order. The clipped black is left out; so is the
    /// clipped white (both as the panel's plot always drew it).
    init(counts: [[Float]], clipsWhite: Bool) {
        let counts: [[Float]] = counts.map { row in
            var row = row
            row[0] = 0; row[1] = 0
            if clipsWhite { row[254] = 0; row[255] = 0 }
            return row
        }
        let lines = counts.map { Self.smoothed($0, sigma: 1.2) }
        let top = max(1, counts.map { Self.smoothed($0, sigma: 6).max() ?? 0 }.max() ?? 0) * 1.1
        self.top = top
        rows = lines.map { row in row.map { min(1, ($0 / top).squareRoot()) } }
    }

    /// Bins across the plot.
    var binCount: Int { rows.first?.count ?? 0 }

    subscript(channel: Layer2Histogram.Channel) -> [Float] { rows[channel.rawValue] }

    /// A Gaussian of `sigma` bins across the row, the ends held at the row's own ends.
    private static func smoothed(_ row: [Float], sigma: Float) -> [Float] {
        let r = Int(3 * sigma) + 1
        let kernel = (-r...r).map { exp(-0.5 * pow(Float($0) / sigma, 2)) }
        let sum = kernel.reduce(0, +)
        return row.indices.map { i in
            var v: Float = 0
            for (j, k) in kernel.enumerated() { v += k * row[min(max(i + j - r, 0), row.count - 1)] }
            return v / sum
        }
    }
}
