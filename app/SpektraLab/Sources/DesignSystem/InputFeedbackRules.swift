import Foundation

/// Decide once: vertical intent never mutates the control later in the gesture.
struct DragOwnership {
    enum Axis { case undecided, horizontal, vertical }
    /// How far a drag must move before it is called horizontal or vertical. 8 points is the
    /// touch's own; a Mac's mouse needs none of it (the owner, 2026-11-10: a slider that would not
    /// move until the pointer had travelled far enough felt "welded" to the track).
    var threshold: Double = 8
    private(set) var axis = Axis.undecided
    mutating func update(x: Double, y: Double) -> Bool {
        if axis == .undecided, max(abs(x), abs(y)) >= threshold {
            axis = abs(x) > abs(y) * 1.25 ? .horizontal : .vertical
        }
        return axis == .horizontal
    }
}
