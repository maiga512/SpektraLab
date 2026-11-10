"""The finish path (`finish_only`): a finished picture, grain and the strip, no film.

What this holds the engine to, in three checks:

1. **The identity.** With the grain off and no strip, the path returns the
   picture it was given. A photograph graded elsewhere must not be re-graded
   by turning the film and the paper off -- if this drifts, the switch in the
   app is a lie.

2. **Grain that is grain.** With it on, the difference is per-pixel, its mean
   over a block falls away while the per-pixel rms does not, and the picture's
   own colour is left where it was (no cast, no shift in the mean).

3. **The strip.** With a film edge on, the canvas is the strip, and the gate's
   pixels are still the picture the path was given.

    python3 tests/finish_checks.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spk_ctypes import Engine  # noqa: E402

HERE = Path(__file__).resolve().parent
# A real photograph, the demo library's own: sRGB, 8 bits, already graded.
PHOTO = HERE.parents[1] / "app" / "SpektraLab" / "SampleSources" / "scene_raw_srgb.jpg"

BASE = {
    "film_stock": "kodak_portra_400",
    "print_stock": "kodak_portra_endura",
    "finish_only": True,
    "auto_exposure": False,
    "exposure_compensation_ev": 0.0,
    "input_color_space": "sRGB",
    "input_cctf_decoding": True,
    "output_color_space": "sRGB",
    "output_cctf_encoding": True,
    "grain_active": False,
    "halation_active": False,
    "dir_couplers_active": False,
    "overscan_active": False,
    "date_imprint_active": False,
}


def load_photo(long_edge: int = 900) -> np.ndarray:
    """A real JPEG where Pillow and the demo library are here; a synthetic frame
    otherwise, so the checks still run on a bare host (they lose the "a real
    photograph, already graded" half and say so)."""
    try:
        from PIL import Image

        image = Image.open(PHOTO).convert("RGB")
        image.thumbnail((long_edge, long_edge))
        return np.asarray(image).astype(np.float32) / 255.0
    except Exception as why:  # no Pillow, or the demo library's sources are not here
        print(f"  note  no photograph ({why}); a synthetic frame stands in")
        h, w = long_edge * 2 // 3, long_edge
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)
        img = np.stack([0.05 + 0.85 * x / (w - 1), 0.05 + 0.85 * y / (h - 1),
                        0.2 + 0.6 * (1 - x / (w - 1)) * (y / (h - 1))], -1)
        img[h // 6:h // 3, w // 8:w // 3] = [0.62, 0.18, 0.12]
        return np.clip(img, 0.0, 1.0).astype(np.float32)


def render(photo: np.ndarray, **params):
    with Engine() as engine:
        with engine.open(photo, {**BASE, **params}) as session:
            rgba, _ = session.render("live")
            geometry = session.overscan_geometry() if params.get("overscan_active") else None
    return rgba[:, :, :3].astype(np.float64) / 65535.0, geometry


def main() -> int:
    photo = load_photo()
    failures: list[str] = []

    def check(ok: bool, what: str) -> None:
        print(("  ok    " if ok else "  FAIL  ") + what)
        if not ok:
            failures.append(what)

    # ---- 1. the identity -------------------------------------------------
    print("identity, grain off and no strip")
    out, _ = render(photo)
    d = np.abs(out - photo.astype(np.float64))
    check(out.shape == photo.shape, f"the picture keeps its size ({out.shape} against {photo.shape})")
    check(d.max() < 1.5 / 255, f"the picture is returned unchanged, max {d.max() * 255:.2f} / 255")

    # ---- 2. grain --------------------------------------------------------
    print("grain, the stock's own particles")
    grained, _ = render(photo, grain_active=True, grain_sublayers_active=True)
    delta = grained - photo.astype(np.float64)
    rms = float(np.sqrt((delta ** 2).mean()))
    k = 16
    h, w = (delta.shape[0] // k) * k, (delta.shape[1] // k) * k
    blocks = delta[:h, :w].reshape(h // k, k, w // k, k, 3).mean(axis=(1, 3))
    block_rms = float(np.sqrt((blocks ** 2).mean()))
    check(rms > 0.002, f"there is grain, rms {rms:.4f}")
    check(block_rms < rms / 2, f"and it averages away over {k}x{k}, {block_rms:.4f} against {rms:.4f}")
    shift = grained.mean(axis=(0, 1)) - photo.astype(np.float64).mean(axis=(0, 1))
    check(np.abs(shift).max() < 0.004, "the picture's mean colour is kept, shift "
          + " ".join(f"{v:+.4f}" for v in shift))

    # ---- 2b. the white balance -------------------------------------------
    print("the decode's white balance, on the finished picture")
    neutral, _ = render(photo, scene_wb_temperature=6500.0, scene_wb_tint=0.0)
    check(np.abs(neutral - photo).max() < 1.5 / 255,
          "6500 K and 0 tint are the identity, max %.2f / 255" % (np.abs(neutral - photo).max() * 255))
    # The direction is `CIRAWFilter`'s, measured on a real CR3 (2026-11-10):
    # low temperature = cool picture, high = warm — the ruler's gradient is
    # drawn blue at 2000 K and orange at 10000 K for the same reason.
    m0 = photo.mean(axis=(0, 1))
    cool, _ = render(photo, scene_wb_temperature=3000.0)
    m1 = cool.mean(axis=(0, 1))
    check(m1[2] > m0[2] and m1[0] < m0[0],
          "3000 K is a cool picture, as the RAW decoder makes it (R %+.3f, B %+.3f)" % (m1[0] - m0[0], m1[2] - m0[2]))
    check(abs(cool.mean() - photo.mean()) < 0.02,
          "and its luminance is held (%.4f against %.4f)" % (cool.mean(), photo.mean()))
    warm, _ = render(photo, scene_wb_temperature=9000.0)
    m1 = warm.mean(axis=(0, 1))
    check(m1[0] > m0[0] and m1[2] < m0[2],
          "9000 K is a warm picture, as the RAW decoder makes it (R %+.3f, B %+.3f)" % (m1[0] - m0[0], m1[2] - m0[2]))
    green, _ = render(photo, scene_wb_tint=-100.0)
    check(green.mean(axis=(0, 1))[1] > m0[1],
          "-100 tint is green, as the RAW decoder makes it (G %+.3f)" % (green.mean(axis=(0, 1))[1] - m0[1]))
    magenta, _ = render(photo, scene_wb_tint=100.0)
    check(magenta.mean(axis=(0, 1))[1] < m0[1],
          "+100 tint is magenta, as the RAW decoder makes it (G %+.3f)" % (magenta.mean(axis=(0, 1))[1] - m0[1]))

    # ---- 3. the strip ----------------------------------------------------
    print("the strip, 135 at print")
    stripped, geometry = render(photo, grain_active=True, grain_sublayers_active=True,
                                overscan_active=True, overscan_format="135", overscan_mode="strip")
    check(stripped.shape[0] > photo.shape[0] and stripped.shape[1] > photo.shape[1],
          f"the canvas is the strip ({stripped.shape[1]}x{stripped.shape[0]})")
    gates = []
    if geometry:
        for key in ("gates", "frames", "gates_norm"):
            if key in geometry:
                gates = geometry[key]
                break
    if not gates:
        print("  note  no gate rectangles in the geometry reply:", sorted(geometry or {}))
    else:
        # A gate is a quad of eight normalised numbers (four corners), top-left origin.
        hh, ww = stripped.shape[:2]
        g = np.asarray(gates[0], dtype=np.float64).reshape(-1, 2)
        x0, x1 = int(g[:, 0].min() * ww), int(np.ceil(g[:, 0].max() * ww))
        y0, y1 = int(g[:, 1].min() * hh), int(np.ceil(g[:, 1].max() * hh))
        inside = stripped[y0:y1, x0:x1]
        check(inside.size > 0 and inside.std() > 0.02,
              f"the gate holds a picture ({x1 - x0}x{y1 - y0})")
        shift = inside.mean(axis=(0, 1)) - photo.astype(np.float64).mean(axis=(0, 1))
        check(np.abs(shift).max() < 0.03,
              "and it is the picture that went in, shift " + " ".join(f"{v:+.4f}" for v in shift))

    # ---- 4. the edge print ------------------------------------------------
    print("the strip's lettering, 120 at 6x4.5")
    # The factory's edge print is its own exposure in the film chain; the finish
    # path adds it itself (found on the owner's strip, 2026-11-10, where a 645
    # rebate came out blank). A rebate with the film's name on it differs from
    # one without, and that is the whole check.
    gate = 41.5 / 56.0
    hh, ww = photo.shape[:2]
    if hh / ww > gate:
        n = int(ww * gate); crop = photo[(hh - n) // 2:(hh - n) // 2 + n]
    else:
        n = int(hh / gate); crop = photo[:, (ww - n) // 2:(ww - n) // 2 + n]
    strip = dict(crop_active=True, overscan_active=True, overscan_format="120_645",
                 overscan_mode="strip", overscan_f_number=2.8)
    named, _ = render(crop, grain_active=True, grain_sublayers_active=True,
                      overscan_edge_text="KODAK PORTRA 400", **{k: v for k, v in strip.items() if k != "crop_active"})
    blank, _ = render(crop, grain_active=True, grain_sublayers_active=True,
                      overscan_edge_text="", **{k: v for k, v in strip.items() if k != "crop_active"})
    check(named.shape == blank.shape and np.abs(named - blank).max() > 0.02,
          "the strip carries the film's name, max delta %.3f" % np.abs(named - blank).max())

    print(f"finish checks: {'failed' if failures else 'passed'}"
          + ("" if failures else ", 0 failed"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
