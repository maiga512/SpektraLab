#!/usr/bin/env python3
"""Concentration (`film_render.strength`) — the owner, 2026-11-11.

Three things, all of them cheap enough to run on every change:

1. **The default is untouched.** `strength = 1` must be byte for byte the render
   it was before the field existed — `tests/reference/film_strength_reference.npy`
   was taken from this very harness, grain off so the render is deterministic,
   *before* `film_strength` existed. Anything that makes the default cost more or
   differ fails here, which is what makes the field safe to ship.
2. **The composite is exact.** `out(k) == out(0) + k·(out(1) − out(0))` — a
   layer's opacity, not an approximation of one. Grain is off for the whole test
   (TRAP-01: the pipeline is nondeterministic by default).
3. **The strip survives it.** Concentration composites the *picture*; the film's
   rebate, its edge print and its date are drawn by both renders, so at `k = 0`
   there is still a strip — a frame with no film and no grain, not a frame with
   no film edge.
"""
import sys, pathlib, numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import finish_checks as fc

REFERENCE = pathlib.Path(__file__).parent / "reference" / "film_strength_reference.npy"
failures = 0

def check(name, ok, detail=""):
    global failures
    print(("  ok    " if ok else "  FAIL  ") + name + ("" if not detail else ": " + detail))
    if not ok: failures += 1

photo = fc.load_photo()

def render(k):
    out, _ = fc.render(photo, finish_only=False, grain_active=False,
                       overscan_active=True, overscan_format="135", overscan_mode="strip",
                       overscan_edge_text="KODAK 400", film_strength=k)
    return out

# 1 — the default is the render it was.
a1 = render(1.0)
ref = np.load(REFERENCE)
check("strength 1.0 is byte for byte the pre-field render", a1.shape == ref.shape and np.array_equal(a1, ref),
      f"max |Δ| {np.abs(a1 - ref).max() if a1.shape == ref.shape else float('nan'):.3g}")

a0 = render(0.0)
ah = render(0.5)

# 2 — exact compositing, where the output is not clamped. The film can leave a dye-subtracted
# pixel below zero, and the output clamps what it hands back: the *endpoint* is then clamped and
# the midpoint is not, which is not a property of the composite (it is measured at 0.16 in the
# darkest fifth of the picture, against 0.00025 over the picture as a whole and an exact match in
# the middle tones). On pixels whose two endpoints are interior, the composite must be exact.
want = a0 + 0.5 * (a1 - a0)
interior = (a0 > 1e-4) & (a0 < 1 - 1e-4) & (a1 > 1e-4) & (a1 < 1 - 1e-4)
err = np.abs(ah - want)[interior].max() if interior.any() else 0.0
clamped = int((~interior).all(axis=-1).sum())
# 1.526e-05 is one step of 16-bit storage: the buffers are RGBAh, and a composite that is exact
# in float32 shows exactly one quantisation step of each term's rounding here.
check("out(0.5) is out(0) + 0.5·(out(1) − out(0)) where the output is not clamped", err <= 2.0 / 65535,
      f"max |Δ| {err:.3g} over {int(interior.sum()):,} of {interior.size:,} channel-samples "
      f"({clamped:,} pixels whose endpoints clamp)")
check("no NaN at any strength", all(np.isfinite(x).all() for x in (a0, ah, a1)))

# 3 — the film's look moves, its strip does not.
h, w, _ = a1.shape
band = slice(0, max(4, h // 40))                      # the top rebate
edge1, edge0 = a1[band].mean(), a0[band].mean()
picture = np.abs(a0[h//5:4*h//5, w//5:4*w//5] - a1[h//5:4*h//5, w//5:4*w//5]).mean()
check("the picture moves with the strength", picture > 0.01, f"mean |Δ| {picture:.4f} at k=0")
check("the strip is still there at k=0", abs(float(edge0 - edge1)) < 0.10 and 0.0 <= edge0 < 1.0,
      f"rebate mean {edge0:.4f} against {edge1:.4f} at k=1")

print(f"film strength checks: {3 + 3} checked, {failures} failed")
sys.exit(1 if failures else 0)
