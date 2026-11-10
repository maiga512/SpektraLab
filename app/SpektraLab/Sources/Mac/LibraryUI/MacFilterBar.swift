//  MacFilterBar.swift — the library's filter bar: the entry by the count, and the conditions under it.
//
//  Capture One's filter bar, in this page's terms (the owner, 2026-11-09): a chip beside the total says
//  whether anything is filtered; opened, it puts a bar under the grid's header — the rating on one line
//  (the `≥` `≤` `=` rule and its stars), the other conditions on the next (colour, work, export, format,
//  shape, date), each a menu of the facets with their counts. Nothing here filters: every change goes to
//  the store's query (`MacLibraryData.apply`), which the helper answers — the sidebar's Filters tool and
//  this bar are two spellings of the same query.
//
//  One rule the bar keeps: a condition that is on says so on its own face (the title carries the value),
//  so the bar reads like the query without opening anything.

import SwiftUI

struct MacFilterBar: View {
    let store: any MacLibraryData
    let browser: MacLibraryBrowser
    /// The store's query, changed and applied. (Taken as a value: the store's `apply` is async.)
    let apply: (MacImageQuery) -> Void

    private func change(_ edit: (inout MacImageQuery) -> Void) {
        var next = store.query
        edit(&next)
        apply(next)
    }

    private var q: MacImageQuery { store.query }
    private var f: MacFacets { store.facets }

    static let height: CGFloat = MacMetric.pt(26) * 2 + MacMetric.pt(8)

    var body: some View {
        VStack(spacing: MacMetric.pt(2)) {
            ratingLine
            conditionLine
        }
        .padding(.horizontal, MacMetric.pt(10))
        .padding(.vertical, MacMetric.pt(3))
        .frame(height: Self.height)
        .background(Theme.panel)
        .overlay(alignment: .bottom) { Rectangle().fill(Theme.wall).frame(height: 1) }
        .accessibilityIdentifier("mac.library.filterBar")
    }

    // MARK: the rating, on its own line

    private var ratingLine: some View {
        HStack(spacing: MacMetric.pt(6)) {
            Text(L("Rating")).font(MacMetric.font(11)).foregroundStyle(Theme.dim)
                .frame(width: MacMetric.pt(54), alignment: .leading)
            // ≥ / ≤ / =: what a star means (Capture One's filter bar). The rule is not a filter by itself.
            HStack(spacing: 0) {
                ForEach(MacRatingRule.allCases, id: \.self) { rule in
                    Button { change { $0.ratingRule = rule } } label: {
                        Text(rule.sign).font(MacMetric.font(11, .semibold))
                            .foregroundStyle(q.ratingRule == rule ? Theme.text : Theme.dim)
                            .frame(width: MacMetric.pt(24), height: MacMetric.pt(18))
                            .background(q.ratingRule == rule ? Theme.card : Color.clear,
                                        in: RoundedRectangle(cornerRadius: MacMetric.pt(4), style: .continuous))
                    }
                    .buttonStyle(.plain)
                    .help(rule.title)
                }
            }
            .padding(1)
            .background(Theme.card, in: RoundedRectangle(cornerRadius: MacMetric.pt(5), style: .continuous))

            ForEach(starRows, id: \.value) { star in
                starButton(star)
            }
            Spacer(minLength: 0)
            if q.isFiltered {
                Button { change { $0 = $0.cleared } } label: {
                    Text(L("Clear Filters")).font(MacMetric.font(11)).foregroundStyle(Theme.accent)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func starButton(_ star: Star) -> some View {
        let on = starOn(star.value)
        return Button { change { toggleStar(&$0, star.value) } } label: {
            starLabel(star, on: on)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(star.value == 0 ? L("No Rating") : MacWords.rating(star.value))
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    private func starLabel(_ star: Star, on: Bool) -> some View {
        HStack(spacing: MacMetric.pt(3)) {
            Text(star.value == 0 ? L("None") : String(repeating: "★", count: star.value))
                .font(MacMetric.font(11))
            if star.count > 0 {
                Text("\(star.count)").font(MacMetric.font(9)).foregroundStyle(Theme.dim)
            }
        }
        .foregroundStyle(on ? Theme.text : Theme.dim)
        .padding(.horizontal, MacMetric.pt(5))
        .frame(height: MacMetric.pt(18))
        .background(on ? Theme.card : Color.clear,
                    in: RoundedRectangle(cornerRadius: MacMetric.pt(4), style: .continuous))
    }

    private struct Star: Hashable { let value: Int; let count: Int }

    /// The star values the facet counts: 5 … 0, whatever the collection holds.
    private var starRows: [Star] {
        (0...5).reversed().map { value in Star(value: value, count: f.ratings.first { $0.value == value }?.count ?? 0) }
    }

    private func starOn(_ value: Int) -> Bool {
        switch q.ratingRule {
        case .atLeast: q.minimumRating == value
        case .atMost: q.maximumRating == value
        case .exactly: q.ratings == [value]
        }
    }

    private func toggleStar(_ q: inout MacImageQuery, _ value: Int) {
        switch q.ratingRule {
        case .atLeast: q.minimumRating = q.minimumRating == value ? nil : value
        case .atMost: q.maximumRating = q.maximumRating == value ? nil : value
        case .exactly: q.ratings = q.ratings == [value] ? [] : [value]
        }
    }

    // MARK: the other conditions, on the next

    private var conditionLine: some View {
        ScrollView(.horizontal) {
            HStack(spacing: MacMetric.pt(6)) {
                flagMenu
                colourMenu
                editMenu
                exportMenu
                kindMenu
                aspectMenu
                dateMenu
                Spacer(minLength: 0)
            }
        }
        .scrollIndicators(.hidden)
        .frame(height: MacMetric.pt(20))
    }

    /// A menu's face: its name, and what it is set to where it is set.
    private func face(_ title: String, _ value: String?) -> some View {
        HStack(spacing: MacMetric.pt(4)) {
            Text(title).font(MacMetric.font(11)).foregroundStyle(value == nil ? Theme.text : Theme.accent)
            if let value {
                Text(value).font(MacMetric.font(11, .semibold)).foregroundStyle(Theme.accent)
            }
            Image(systemName: "chevron.down").font(MacMetric.font(8)).foregroundStyle(Theme.dim)
        }
        .frame(height: MacMetric.pt(18))
    }

    private func item(_ title: String, count: Int, on: Bool, _ toggle: @escaping () -> Void) -> some View {
        Button(action: toggle) {
            HStack {
                Text(on ? "✓ " + title : title)
                Spacer(minLength: MacMetric.pt(12))
                Text("\(count)").foregroundStyle(Theme.dim)
            }
        }
    }

    private var flagMenu: some View {
        Menu {
            item(MacPickFlag.picked.title, count: f.picked, on: q.pickStates.contains(.picked)) {
                change { Self.flip(&$0.pickStates, .picked) }
            }
            item(MacPickFlag.rejected.title, count: f.rejected, on: q.pickStates.contains(.rejected)) {
                change { Self.flip(&$0.pickStates, .rejected) }
            }
        } label: { face(L("Flag"), flagFace) }
    }

    private var flagFace: String? {
        guard !q.pickStates.isEmpty else { return nil }
        return MacPickFlag.allCases.filter(q.pickStates.contains).map(\.title).joined(separator: ", ")
    }

    private var colourMenu: some View {
        Menu {
            // Every label the app knows, with its count (0 where none): a menu that grew and shrank
            // with the collection could not be learned (the owner, 2026-11-10: "那个几个颜色，你也没做出来").
            ForEach(MacColorLabel.allCases, id: \.rawValue) { c in
                item(MacWords.colorName(c.rawValue), count: colourCount(c.rawValue), on: q.colorLabels.contains(c.rawValue)) {
                    change { $0.colorLabels.formSymmetricDifference([c.rawValue]) }
                }
            }
        } label: {
            face(L("Colour Label"), colourFace)
        }
    }

    private func colourCount(_ tag: Int) -> Int {
        f.colorLabels.first { $0.value == tag }?.count ?? 0
    }

    private var colourFace: String? {
        guard !q.colorLabels.isEmpty else { return nil }
        return q.colorLabels.sorted().map(MacWords.colorName).joined(separator: ", ")
    }

    private var editMenu: some View {
        Menu {
            item(MacEditState.edited.title, count: f.edited, on: q.editStates.contains(.edited)) {
                change { Self.flip(&$0.editStates, .edited) }
            }
            item(MacEditState.unedited.title, count: f.unedited, on: q.editStates.contains(.unedited)) {
                change { Self.flip(&$0.editStates, .unedited) }
            }
        } label: { face(L("Edit Status"), editFace) }
    }

    private var editFace: String? {
        switch (q.editStates.contains(.edited), q.editStates.contains(.unedited)) {
        case (true, false): MacEditState.edited.title
        case (false, true): MacEditState.unedited.title
        default: nil
        }
    }

    private var exportMenu: some View {
        Menu {
            item(MacExportState.exported.title, count: f.exported, on: q.exportStates.contains(.exported)) {
                change { Self.flip(&$0.exportStates, .exported) }
            }
            item(MacExportState.notExported.title, count: f.notExported, on: q.exportStates.contains(.notExported)) {
                change { Self.flip(&$0.exportStates, .notExported) }
            }
        } label: { face(L("Export Status"), exportFace) }
    }

    private var exportFace: String? {
        switch (q.exportStates.contains(.exported), q.exportStates.contains(.notExported)) {
        case (true, false): MacExportState.exported.title
        case (false, true): MacExportState.notExported.title
        default: nil
        }
    }

    private var kindMenu: some View {
        Menu {
            ForEach(f.kinds, id: \.value) { v in
                let kind = MacImage.FileKind(rawValue: v.value)
                item(MacWords.kind(v.value), count: v.count, on: kind.map(q.kinds.contains) ?? false) {
                    if let kind { change { $0.kinds.formSymmetricDifference([kind]) } }
                }
            }
        } label: { face(L("Format"), kindFace) }
    }

    private var kindFace: String? {
        guard !q.kinds.isEmpty else { return nil }
        return q.kinds.map(\.rawValue).sorted().map(MacWords.kind).joined(separator: ", ")
    }

    private struct AspectRow: Hashable { let aspect: MacAspect; let count: Int }

    private var aspectRows: [AspectRow] {
        f.aspects.compactMap { v in
            MacAspect(rawValue: v.value).map { AspectRow(aspect: $0, count: v.count) }
        }
    }

    private var aspectMenu: some View {
        Menu {
            ForEach(aspectRows, id: \.aspect) { row in
                item(row.aspect.title, count: row.count, on: q.aspects.contains(row.aspect)) {
                    change { Self.flip(&$0.aspects, row.aspect) }
                }
            }
        } label: { face(L("Composition"), aspectFace) }
    }

    private var aspectFace: String? {
        guard !q.aspects.isEmpty else { return nil }
        return MacAspect.allCases.filter(q.aspects.contains).map(\.title).joined(separator: ", ")
    }

    private var dateMenu: some View {
        Menu {
            ForEach(f.years.sorted { $0.value > $1.value }, id: \.value) { y in
                let from = "\(y.value)-01-01", to = "\((Int(y.value) ?? 0) + 1)-01-01"
                item(y.value, count: y.count, on: q.capturedFrom == from && q.capturedTo == to) {
                    change { next in
                        if next.capturedFrom == from && next.capturedTo == to {
                            next.capturedFrom = nil
                            next.capturedTo = nil
                        } else {
                            next.capturedFrom = from
                            next.capturedTo = to
                        }
                    }
                }
            }
        } label: { face(L("Date"), dateFace) }
    }

    private var dateFace: String? {
        guard let from = q.capturedFrom else { return nil }
        return String(from.prefix(4))
    }

    static func flip<T: Hashable>(_ set: inout Set<T>, _ value: T) {
        if set.contains(value) { set.remove(value) } else { set.insert(value) }
    }
}
