//  LibraryFilterIndex.swift — the two filters the helper cannot answer by itself.
//
//  The helper owns ratings, colour tags, kinds, dates, cameras, lenses, keywords and "has an edit"
//  (`has_edit`). Two things the person filters by here are the app's own:
//
//  - **Shape** (landscape, portrait, square). The helper's rows carry the pixel size, but it has no
//    facet for the shape and no filter key: it is arithmetic on `width x height`, and it is done
//    here, over the collection's rows read once.
//  - **Exported** (2026-11-09). Nothing in the library or the helper records that a picture has
//    left the app — `ExportService` writes a line here when a batch writes a file, and a filter on
//    it is this book's set of paths read against the rows.
//
//  Both end the same way: a set of image uuids handed to the helper as `images[]` (the channel
//  `developedOnly` already uses), so the helper still counts, sorts and pages. This file decides
//  only *which* uuids; it never renders and never opens a file.

import Foundation
import os

/// A picture's shape, in the Filters tool's words.
enum MacAspect: String, CaseIterable, Sendable {
    case landscape, portrait, square

    var title: String {
        switch self {
        case .landscape: L("Landscape Photo")
        case .portrait: L("Portrait Photo")
        case .square: L("Square Photo")
        }
    }

    /// A picture's shape from its pixel size. A square is one whose sides differ by no more than a
    /// pixel — a crop lands on one — and anything taller than wide is a portrait.
    static func of(_ size: PixelSize?) -> MacAspect? {
        guard let size, size.width > 0, size.height > 0 else { return nil }
        if abs(size.width - size.height) <= 1 { return .square }
        return size.width > size.height ? .landscape : .portrait
    }
}

/// Every file an export has written, by the path the library lists the picture under.
///
/// Written once per saved file (`ExportService`), kept in `Application Support/<bundle id>/MacLibrary/`
/// beside the sources list. Nothing is removed from it: a picture exported once is exported, and a
/// later export only moves its date. A path that is not here has never been exported by this app —
/// exports another program made are not knowable, and are not pretended to be.
@MainActor
final class ExportLedger {
    static let shared = ExportLedger()

    /// Bumped when a path is written, so a page filtered on it knows to ask again.
    private(set) var revision = 0

    private var saved: [String: Date] = [:]
    private var loaded = false
    private let url = ImportService.root.appending(path: "MacLibrary/exports.json")
    private let log = Logger(subsystem: "com.spektralab.mac", category: "exports")

    /// Whether the file at `path` has been exported by this app.
    func has(_ path: String) -> Bool { has(key: CatalogSourcesStore.key(path)) }
    func has(key: String) -> Bool { load(); return saved[key] != nil }

    /// Every path it holds, for a filter that is not on the main actor to read.
    var keys: Set<String> { load(); return Set(saved.keys) }

    /// The picture of a frame an export wrote: its own file, and the pair's `.spektrapair` where it
    /// is one (the library lists a pair under that file).
    func record(frame: LibraryFrame) {
        var paths: [URL] = []
        if let url = frame.picture.fileURL { paths.append(url) }
        if frame.isPair { paths.append(CatalogSourcesStore.pairFile(frame)) }
        record(paths: paths)
    }

    func record(paths: [URL]) {
        guard !paths.isEmpty else { return }
        load()
        let now = Date()
        for u in paths { saved[CatalogSourcesStore.key(u.path)] = now }
        revision &+= 1
        save()
    }

    // MARK: the book

    private func load() {
        guard !loaded else { return }
        loaded = true
        guard let data = try? Data(contentsOf: url),
              let book = try? JSONDecoder().decode([String: Date].self, from: data) else { return }
        saved = book
    }

    private func save() {
        do {
            try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys]
            try encoder.encode(saved).write(to: url, options: .atomic)
        } catch {
            log.error("the export book could not be written: \(error.localizedDescription, privacy: .public)")
        }
    }
}

/// A collection's rows reduced to what the app-side filters read: each picture's path and shape.
///
/// Read once per collection (`CatalogSourcesStore.filterIndex`) and thrown away when the collection,
/// the source's rows or the export book change. `rows` is keyed by the helper's image uuid — what
/// `images[]` takes — and holds nothing of the pixels.
struct LibraryFilterIndex: Sendable {
    struct Row: Sendable {
        let pathKey: String
        let aspect: MacAspect?
    }

    var rows: [String: Row] = [:]

    /// The uuids whose shape is one of `aspects` (all, where the set is empty).
    func ids(aspects: Set<MacAspect>) -> Set<String> {
        guard !aspects.isEmpty else { return Set(rows.keys) }
        return Set(rows.filter { _, row in row.aspect.map(aspects.contains) ?? false }.keys)
    }

    /// The uuids whose file the export book does and does not list. The book's paths are read on
    /// the main actor and handed in (`ExportLedger.keys`): this type is plain data.
    func ids(exported: Bool, written: Set<String>) -> Set<String> {
        Set(rows.filter { _, row in written.contains(row.pathKey) == exported }.keys)
    }

    /// Counts for the panel, over the whole scope: shape, then the export book.
    func aspectCounts() -> [(MacAspect, Int)] {
        MacAspect.allCases.compactMap { a in
            let n = rows.values.reduce(0) { $0 + ($1.aspect == a ? 1 : 0) }
            return n == 0 ? nil : (a, n)
        }
    }

    /// The uuids wearing one of these flags (none: every row).
    func ids(flags: Set<MacPickFlag>, marked: [MacPickFlag: Set<String>]) -> Set<String> {
        guard !flags.isEmpty else { return Set(rows.keys) }
        let keys = flags.reduce(into: Set<String>()) { $0.formUnion(marked[$1] ?? []) }
        return Set(rows.filter { _, row in keys.contains(row.pathKey) }.keys)
    }

    func flagCounts(marked: [MacPickFlag: Set<String>]) -> (picked: Int, rejected: Int) {
        func count(_ flag: MacPickFlag) -> Int {
            let keys = marked[flag] ?? []
            return rows.values.reduce(0) { $0 + (keys.contains($1.pathKey) ? 1 : 0) }
        }
        return (count(.picked), count(.rejected))
    }

    func exportCounts(written: Set<String>) -> (exported: Int, notExported: Int) {
        var yes = 0
        for row in rows.values where written.contains(row.pathKey) { yes += 1 }
        return (yes, rows.count - yes)
    }
}

/// A picture's flag: the person's own mark, kept here and nowhere else. Lightroom and Capture One keep
/// theirs in their own catalogs and never write them to XMP, so this book is the one place the two
/// marks can differ; nothing is claimed to travel with the file.
enum MacPickFlag: String, CaseIterable, Codable, Sendable {
    case picked, rejected

    var title: String {
        switch self {
        case .picked: L("Picked")
        case .rejected: L("Rejected")
        }
    }
}

/// The flags set in the window library, by the path the library lists a picture under.
///
/// Kept in `Application Support/<bundle id>/MacLibrary/flags.json` beside the export book. A flag set
/// here stays here: the file, its sidecar and its catalog are not written.
@MainActor
final class PickFlags {
    static let shared = PickFlags()

    private(set) var revision = 0
    private var marks: [String: MacPickFlag] = [:]
    private var loaded = false
    private let url = ImportService.root.appending(path: "MacLibrary/flags.json")
    private let log = Logger(subsystem: "com.spektralab.mac", category: "flags")

    func flag(for path: String) -> MacPickFlag? { load(); return marks[CatalogSourcesStore.key(path)] }
    func flag(forKey key: String) -> MacPickFlag? { load(); return marks[key] }

    /// Every path wearing `flag`.
    var keys: [MacPickFlag: Set<String>] {
        load()
        var out: [MacPickFlag: Set<String>] = [:]
        for (key, flag) in marks { out[flag, default: []].insert(key) }
        return out
    }

    /// The flag a menu press should leave: pressed again, it clears.
    func set(_ flag: MacPickFlag?, for paths: [URL]) {
        guard !paths.isEmpty else { return }
        load()
        for u in paths {
            let key = CatalogSourcesStore.key(u.path)
            if flag == nil { marks[key] = nil } else { marks[key] = flag }
        }
        revision &+= 1
        save()
    }

    private func load() {
        guard !loaded else { return }
        loaded = true
        guard let data = try? Data(contentsOf: url),
              let book = try? JSONDecoder().decode([String: MacPickFlag].self, from: data) else { return }
        marks = book
    }

    private func save() {
        do {
            try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys]
            try encoder.encode(marks).write(to: url, options: .atomic)
        } catch {
            log.error("the flag book could not be written: \(error.localizedDescription, privacy: .public)")
        }
    }
}
