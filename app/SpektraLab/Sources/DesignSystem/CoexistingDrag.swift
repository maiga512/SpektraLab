//  CoexistingDrag.swift — a drag a scroll view may run beside.
//
//  Built with the the operating system 26 SDK, SwiftUI's `simultaneousGesture` is no longer simultaneous
//  with an ancestor's gesture: Apple's release note calls the old behaviour the bug
//  (147970990), and the change took the Develop page's scrolling with it. On the host a
//  finger dragging on a slider, a ruler or the curve was swallowed whole and the panel
//  would not move — while on this Mac a scroll wheel never meets a gesture at all, so
//  every panel looked fine there (the owner, 2026-10-15: "every subpage of them cannot
//  be scrolled on real device"). Apple's advice on the report of it (FB18199844) is a
//  UIKit recogniser rather than a SwiftUI gesture: a zero-delay, unbounded
//  `UILongPressGestureRecognizer` whose delegate allows simultaneous recognition, which
//  the scroll view's pan then obeys.
//
//  `dragBesideScroll` is that recogniser. `onChanged` receives the drag from where it
//  began — the shape the callers already kept for `DragGesture` — and `beginsOn` may
//  refuse a touch by where it starts: the curve takes a finger only in point mode, and
//  every other finger scrolls the panel.
//
//  the operating system 17 fallback: the old `simultaneousGesture`, kept only for a device too old to run
//  `UIGestureRecognizerRepresentable` (the operating system 18). There the panels block again — no such
//  device is in the beta.

import SwiftUI
import UIKit

/// Where a pointer is a mouse: no touch to arbitrate, no scroll gesture to share.
enum MacInput {
    static var takesDragAtOnce: Bool {
        ProcessInfo.processInfo.isiOSAppOnMac || UIDevice.current.userInterfaceIdiom == .mac
    }
}

/// The drag's life as the callers knew it from `DragGesture`.
struct CoexistingDragValue {
    var start: CGPoint
    var location: CGPoint
    var translation: CGSize
}

@available(iOS 18.0, *)
struct CoexistingDrag: UIGestureRecognizerRepresentable {
    var beginsOn: ((CGPoint) -> Bool)?
    var onChanged: (CoexistingDragValue) -> Void
    var onEnded: (CoexistingDragValue) -> Void

    final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        var beginsOn: ((CGPoint) -> Bool)?
        var start: CGPoint?

        func gestureRecognizerShouldBegin(_ recognizer: UIGestureRecognizer) -> Bool {
            guard let beginsOn, let view = recognizer.view else { return true }
            return beginsOn(recognizer.location(in: view))
        }

        /// The whole point: the scroll view's pan keeps working beside this.
        func gestureRecognizer(_ recognizer: UIGestureRecognizer,
                               shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer) -> Bool { true }
    }

    func makeCoordinator(converter: CoordinateSpaceConverter) -> Coordinator { Coordinator() }

    func makeUIGestureRecognizer(context: Context) -> UILongPressGestureRecognizer {
        let recognizer = UILongPressGestureRecognizer()
        recognizer.minimumPressDuration = 0
        recognizer.allowableMovement = .greatestFiniteMagnitude
        recognizer.delegate = context.coordinator
        recognizer.cancelsTouchesInView = false
        return recognizer
    }

    func updateUIGestureRecognizer(_ recognizer: UILongPressGestureRecognizer, context: Context) {
        context.coordinator.beginsOn = beginsOn
    }

    func handleUIGestureRecognizerAction(_ recognizer: UILongPressGestureRecognizer, context: Context) {
        guard let view = recognizer.view else { return }
        let at = recognizer.location(in: view)
        switch recognizer.state {
        case .began:
            context.coordinator.start = at
            onChanged(value(at: at, from: at))
        case .changed:
            guard let start = context.coordinator.start else { return }
            onChanged(value(at: at, from: start))
        case .ended, .cancelled, .failed:
            let start = context.coordinator.start ?? at
            context.coordinator.start = nil
            onEnded(value(at: at, from: start))
        default:
            break
        }
    }

    private func value(at: CGPoint, from start: CGPoint) -> CoexistingDragValue {
        CoexistingDragValue(start: start, location: at,
                            translation: CGSize(width: at.x - start.x, height: at.y - start.y))
    }
}

extension View {
    /// The drag above; on the operating system 17 the `simultaneousGesture` this replaces.
    @ViewBuilder
    func dragBesideScroll(beginsOn: ((CGPoint) -> Bool)? = nil,
                          onChanged: @escaping (CoexistingDragValue) -> Void,
                          onEnded: @escaping (CoexistingDragValue) -> Void = { _ in }) -> some View {
        // **On the Mac a slider takes the pointer at once.** There is no finger to arbitrate with
        // and no scroll to share: the wheel scrolls the panel, so a press on the track is the
        // slider's, with no movement before it is given one (the owner, 2026-11-10: "像焊死一样").
        if MacInput.takesDragAtOnce {
            return AnyView(highPriorityGesture(DragGesture(minimumDistance: 0)
                .onChanged { v in
                    onChanged(CoexistingDragValue(start: v.startLocation, location: v.location, translation: v.translation))
                }
                .onEnded { v in
                    onEnded(CoexistingDragValue(start: v.startLocation, location: v.location, translation: v.translation))
                }))
        }
        if #available(iOS 18.0, *) {
            return AnyView(gesture(CoexistingDrag(beginsOn: beginsOn, onChanged: onChanged, onEnded: onEnded)))
        } else {
            return AnyView(simultaneousGesture(DragGesture(minimumDistance: 8)
                .onChanged { v in onChanged(CoexistingDragValue(start: v.startLocation, location: v.location,
                                                                translation: v.translation)) }
                .onEnded { v in onEnded(CoexistingDragValue(start: v.startLocation, location: v.location,
                                                            translation: v.translation)) }))
        }
    }
}
