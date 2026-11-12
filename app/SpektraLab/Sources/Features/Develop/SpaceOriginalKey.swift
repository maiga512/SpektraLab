//  SpaceOriginalKey.swift — Space held shows the original; release brings the develop back.
//
//  The key form of the gesture `DevelopCanvas` already has (`allowsOriginalHold`'s long-press):
//  Lightroom's Space-hold compare, as `PadDevelopPage`'s header promises (PAGES.md §6a keys).
//
//  **Why a monitor and not only `.onKeyPress`** (which the page also keeps, as its fallback): a
//  SwiftUI plain key needs the page to hold focus, and the page loses it the moment a field does.
//  The window measured the same in 2026-10-26 (`MainWindowLayout`: plain keys through
//  `keyboardShortcut` were dropped by Catalyst, and `.onKeyPress` only ever saw the keys while the
//  view was focused) — so the window's plain keys are `UIKeyCommand`s, and this one is a local
//  `NSEvent` monitor, which sees every space while a develop page is up. The two gates the
//  window's own keys ask are asked here too: **AppKit has not taken the keys** for a panel or an
//  AppKit field editor (`MacAppKitEdit.owns`), and **nobody is typing** (`MacShortcutRegistry.
//  typing` — a space in a text field is a space). Outside them the event is returned untouched:
//  a focused button still activates on space, a panel is never stolen from.
//
//  `NSEvent` is reached through the Objective-C runtime, as `MacScrollZoom` reaches its own
//  monitor: Catalyst links AppKit but no header offers either. One monitor for the app, the way
//  `MacScrollMonitor` is one — installed once, holding a handler only while a page is up.

import SwiftUI
import UIKit

/// The page's Space-hold. `hasOriginal` and `blocked` are read at the event, not at the build.
struct SpaceOriginalKey: ViewModifier {
    let hasOriginal: Bool
    /// An inline crop is open: the page's keys stand down, as `.onKeyPress`'s do.
    let blocked: Bool
    @Binding var original: Bool
    @Binding var comparing: Bool

    func body(content: Content) -> some View {
        content
            .background {
                SpaceOriginalToken { held in
                    if held {
                        // The two silent gates of the three (the monitor's own are logged in
                        // `take`): a hold that does nothing now says which one stopped it
                        // (the owner, 2026-11-12: "有时候不能显示原图").
                        if !hasOriginal || blocked {
                            NSLog("[space-original] held but stood down: hasOriginal=%d blocked=%d",
                                  hasOriginal ? 1 : 0, blocked ? 1 : 0)
                        }
                        guard hasOriginal, !blocked else { return }
                        comparing = false
                        original = true
                    } else if original {
                        original = false
                    }
                }
            }
    }
}

/// The representable that holds the monitor's handler: the last page to appear wins, and going
/// away clears it (the page's own `onChange(of: frame.id)` and `willResignActive` resets then
/// have nothing to undo).
private struct SpaceOriginalToken: UIViewRepresentable {
    let handler: (Bool) -> Void

    final class TokenView: UIView {}

    func makeUIView(context: Context) -> TokenView {
        SpaceOriginalMonitor.shared.holder = handler
        return TokenView()
    }
    func updateUIView(_ view: TokenView, context: Context) {
        SpaceOriginalMonitor.shared.holder = handler
    }
    static func dismantleUIView(_ view: TokenView, coordinator: ()) {
        SpaceOriginalMonitor.shared.holder = nil
    }
}

/// One monitor for the app (`MacScrollMonitor`'s shape): installed when first reached, never
/// removed, and passing everything through — no page, another key, a panel, typing — except the
/// space this page takes.
@MainActor
final class SpaceOriginalMonitor {
    static let shared = SpaceOriginalMonitor()

    /// The develop page's handler; nil with no page up, where every space passes through.
    /// Nil with no page up. Losing the holder ends a hold in the monitor; the page's own resets
    /// (`onChange(of: frame.id)`, `willResignActive`) own `original` itself.
    var holder: ((Bool) -> Void)? {
        didSet { if holder == nil { held = false } }
    }
    /// Whether the taken space is holding: only its own key-up and repeats are swallowed then.
    private(set) var held = false
    private let monitor: AnyObject?

    private init() {
        var made: AnyObject?
        if let cls: AnyClass = NSClassFromString("NSEvent"),
           let method = class_getClassMethod(cls, NSSelectorFromString("addLocalMonitorForEventsMatchingMask:handler:")) {
            typealias Add = @convention(c) (AnyClass, Selector, UInt64, @escaping @convention(block) (AnyObject) -> AnyObject?) -> AnyObject?
            let add = unsafeBitCast(method_getImplementation(method), to: Add.self)
            // NSEventMaskKeyDown = 1 << 10, NSEventMaskKeyUp = 1 << 11.
            let block: @convention(block) (AnyObject) -> AnyObject? = { event in
                MainActor.assumeIsolated { SpaceOriginalMonitor.shared.take(event) }
            }
            made = add(cls, NSSelectorFromString("addLocalMonitorForEventsMatchingMask:handler:"), (1 << 10) | (1 << 11), block)
        }
        monitor = made
        // With no monitor the page's `.onKeyPress` keeps its own (focus-gated) path: the feature
        // degrades to what it was, it never disappears silently — see the header.
    }

    /// The event, or nil where this page takes it. Runs on the main thread, during dispatch.
    private func take(_ object: AnyObject) -> AnyObject? {
        guard let e = object as? NSObject,
              let type = (e.value(forKey: "type") as? NSNumber)?.intValue,
              type == 10 || type == 11,                    // keyDown, keyUp
              let keyCode = (e.value(forKey: "keyCode") as? NSNumber)?.intValue, keyCode == 49 else {
            return object
        }
        if type == 11 {
            // Any space-up ends the hold — whatever came under the finger meanwhile (a shift
            // pressed mid-hold must not leave the original stuck on screen) — and only the press
            // this page took is swallowed.
            guard held else { return object }
            held = false
            holder?(false)
            return nil
        }
        // Held already: an auto-repeat of the same press — ours, and never a control's.
        if held { return nil }
        // keyDown: a page up, no panel has the keys, nobody is typing, no modifier but Caps Lock.
        let flags = (e.value(forKey: "modifierFlags") as? NSNumber)?.uintValue ?? 0
        guard holder != nil,
              flags & 0xFFFF_0000 & ~0x1_0000 == 0,
              !MacShortcutRegistry.shared.typing, !MacAppKitEdit.owns else {
            // A page is up and this space did nothing (the owner, 2026-11-12: "有时候会失效").
            // The gates are all state read at the event, so the reason is only knowable at the
            // event too: log it, so the next time it happens the log says which gate said no
            // instead of a guess. Firing only with a holder means never while no develop page
            // is up — a space in the search field stays out of this.
            if holder != nil {
                NSLog("[space-original] not taken: holder=yes typing=%d appkitOwns=%d flags=%#llx",
                      MacShortcutRegistry.shared.typing ? 1 : 0, MacAppKitEdit.owns ? 1 : 0,
                      UInt64(flags))
            }
            return object
        }
        held = true
        holder?(true)
        return nil
    }
}
