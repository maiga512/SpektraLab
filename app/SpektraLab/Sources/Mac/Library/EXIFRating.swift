//  EXIFRating.swift — the stars a camera wrote into the file's EXIF, which ImageIO does not hand over.
//
//  The owner, 2026-11-09: "my camera's rated pictures — Lightroom reads the stars, this app does not."
//  The stars are EXIF tag 0x4746 (`Rating`, 0–5, EXIF 2.3 and later) and 0x4749 (`RatingPercent`);
//  ImageIO exposes neither — measured on this system: `CGImageSourceCopyPropertiesAtIndex` shows a
//  `{TIFF}` dictionary holding `Make` and not `Rating`, so XMP alone (which `MacHeaders.mark` already
//  reads) missed every camera that writes the stars this way.
//
//  Read here straight from the container's TIFF structure:
//
//  - a TIFF, or a RAW that is a TIFF (NEF, ARW, CR2, DNG): IFD0 at the file's own offset;
//  - a JPEG: its APP1 `Exif\0\0` segment;
//  - anything else (HEIF, CR3): the first bytes searched for `Exif\0\0`, which is where those
//    containers keep the same block.
//
//  Only the IFD is read — a seek and a few hundred bytes — except in the last case, which reads a
//  window. Nothing here decodes a pixel.

import Foundation

enum EXIFRating {
    /// The file's stars, 1…5, or nil when it has none to read.
    nonisolated static func read(_ url: URL) -> Int? {
        guard let handle = try? FileHandle(forReadingFrom: url) else { return nil }
        defer { try? handle.close() }
        guard let head = try? handle.read(upToCount: 16), head.count >= 8 else { return nil }
        if isTIFF(head) { return walk(handle, base: 0) }
        if head[head.startIndex] == 0xFF, head[head.startIndex + 1] == 0xD8 { return jpegExif(handle) }
        return scanForExif(handle)
    }

    private nonisolated static func isTIFF(_ d: Data) -> Bool {
        guard d.count >= 4 else { return false }
        let b = [UInt8](d.prefix(4))
        return (b[0] == 0x49 && b[1] == 0x49 && b[2] == 0x2A && b[3] == 0x00)
            || (b[0] == 0x4D && b[1] == 0x4D && b[2] == 0x00 && b[3] == 0x2A)
    }

    private nonisolated static func jpegExif(_ handle: FileHandle) -> Int? {
        let size = fileSize(handle)
        var offset: UInt64 = 2
        while offset + 4 < size {
            try? handle.seek(toOffset: offset)
            guard let h = try? handle.read(upToCount: 4), h.count == 4 else { return nil }
            let bytes = [UInt8](h)
            guard bytes[0] == 0xFF else { return nil }
            if bytes[1] == 0xDA { return nil }                       // the scan starts: no APP1 left
            let length = Int(bytes[2]) << 8 | Int(bytes[3])
            guard length >= 2 else { return nil }
            if bytes[1] == 0xE1, length >= 8 {
                try? handle.seek(toOffset: offset + 4)
                if let head = try? handle.read(upToCount: 6), head.count == 6, head == Data("Exif\0\0".utf8) {
                    return walk(handle, base: Int(offset) + 10)
                }
            }
            offset += UInt64(2 + length)
        }
        return nil
    }

    private nonisolated static func scanForExif(_ handle: FileHandle) -> Int? {
        let size = fileSize(handle)
        let window = min(size, 8 << 20)
        try? handle.seek(toOffset: 0)
        guard let data = try? handle.read(upToCount: Int(window)) else { return nil }
        guard let r = data.range(of: Data("Exif\0\0".utf8)) else { return nil }
        return walk(handle, base: data.distance(from: data.startIndex, to: r.lowerBound) + 6)
    }

    private nonisolated static func fileSize(_ handle: FileHandle) -> UInt64 {
        (try? handle.seekToEnd()) ?? 0
    }

    private nonisolated static func walk(_ handle: FileHandle, base: Int) -> Int? {
        try? handle.seek(toOffset: UInt64(base))
        guard let head = try? handle.read(upToCount: 8), head.count == 8 else { return nil }
        let big = head[head.startIndex] == 0x4D
        let ifd0 = u32(head, 4, big: big)
        return firstIFD(handle, base: base, at: ifd0, big: big, depth: 0)
    }

    private nonisolated static func firstIFD(_ handle: FileHandle, base: Int, at offset: Int,
                                             big: Bool, depth: Int) -> Int? {
        guard depth < 4, offset > 0 else { return nil }
        try? handle.seek(toOffset: UInt64(base + offset))
        guard let countData = try? handle.read(upToCount: 2), countData.count == 2 else { return nil }
        let count = u16(countData, 0, big: big)
        guard count > 0, count < 4096 else { return nil }
        try? handle.seek(toOffset: UInt64(base + offset + 2))
        guard let entries = try? handle.read(upToCount: count * 12), entries.count == count * 12 else { return nil }
        var rating: Int?
        var percent: Int?
        var subIFD: Int?
        for i in 0..<count {
            let p = i * 12
            let tag = u16(entries, p, big: big)
            let type = u16(entries, p + 2, big: big)
            let n = u32(entries, p + 4, big: big)
            let value = u32(entries, p + 8, big: big)
            switch tag {
            case 0x4746 where (type == 3 || type == 4) && n >= 1:
                rating = type == 3 ? (big ? (value >> 16) : (value & 0xFFFF)) : value
            case 0x4749 where (type == 3 || type == 4) && n >= 1:
                percent = type == 3 ? (big ? (value >> 16) : (value & 0xFFFF)) : value
            case 0x8769:
                subIFD = value
            default: break
            }
        }
        if let rating, (0...5).contains(rating) { return rating }
        if let percent, percent > 0 { return min(5, max(1, (percent + 50) / 100 * 5)) }
        if let subIFD, let r = firstIFD(handle, base: base, at: subIFD, big: big, depth: depth + 1) { return r }
        return nil
    }

    private nonisolated static func u16(_ d: Data, _ i: Int, big: Bool) -> Int {
        let a = Int(d[d.startIndex + i]), b = Int(d[d.startIndex + i + 1])
        return big ? (a << 8 | b) : (b << 8 | a)
    }

    private nonisolated static func u32(_ d: Data, _ i: Int, big: Bool) -> Int {
        let b0 = Int(d[d.startIndex + i]), b1 = Int(d[d.startIndex + i + 1])
        let b2 = Int(d[d.startIndex + i + 2]), b3 = Int(d[d.startIndex + i + 3])
        return big ? (b0 << 24 | b1 << 16 | b2 << 8 | b3) : (b3 << 24 | b2 << 16 | b1 << 8 | b0)
    }
}
