"""The letters edge (无边框片边, owner 2026-11-12): the strip's band is a flat
colour and only the edge print shows.

The design it holds the engine to (verified before writing: the pipeline is
three channels and `spk_to_rgba16` writes alpha opaque, so transparency cannot
ride out of the engine -- the band is a colour on the wire instead):

1. **The wire is accepted.** `overscan_band` and `overscan_edge_ink` are fields
   the engine knows; an engine without them fails the open, which is how this
   file goes red before the feature exists.
2. **The band is the colour asked for.** In letters mode the corners of a
   135 strip come back at the band's own colour -- white here, where the same
   render in strip mode comes back black (the rebate the owner wants gone).
3. **The gate still holds the picture.** The letters mode's gate is the strip
   mode's gate: the picture is not moved, tinted or cut by the band's being
   there.
4. **The print is on the band.** With a near-black custom ink, pixels in the
   band's lettering row are near-black -- not the film's stock orange, so the
   ink is the one asked for and not a five-preset lookup.

    python3 tests/edge_letters_checks.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spk_ctypes import Engine  # noqa: E402

HERE = Path(__file__).resolve().parent
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
    "overscan_active": True,
    "overscan_format": "135",
    "overscan_gate": "square",
    "overscan_camera_seed": 1,
    "overscan_frame_seed": 1,
    "overscan_fog": 0.0,
    "overscan_leaks": 0.0,
    "overscan_edge_text": "SPEKTRA 400",
    "overscan_frame_number": 12,
    "date_imprint_active": False,
}


def load_photo(long_edge: int = 900) -> np.ndarray:
    try:
        from PIL import Image

        image = Image.open(PHOTO).convert("RGB")
        image.thumbnail((long_edge, long_edge))
        return np.asarray(image).astype(np.float32) / 255.0
    except Exception as why:
        print(f"  note  no photograph ({why}); a synthetic frame stands in")
        h, w = long_edge * 2 // 3, long_edge
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)
        img = np.stack([0.05 + 0.85 * x / (w - 1), 0.05 + 0.85 * y / (h - 1),
                        0.2 + 0.6 * (1 - x / (w - 1)) * (y / (h - 1))], -1)
        return np.clip(img, 0.0, 1.0).astype(np.float32)


def render(photo: np.ndarray, **params):
    with Engine() as engine:
        with engine.open(photo, {**BASE, **params}) as session:
            rgba, _ = session.render("live")
    return rgba[:, :, :3].astype(np.float64) / 65535.0


def corners(out: np.ndarray) -> np.ndarray:
    """The four 24 px patches at the canvas' corners: on a 135 strip these are
    the film's corners, well outside the gate and out of the lettering's way."""
    k = 24
    h, w, _ = out.shape
    return np.concatenate([
        out[:k, :k].reshape(-1, 3), out[:k, -k:].reshape(-1, 3),
        out[-k:, :k].reshape(-1, 3), out[-k:, -k:].reshape(-1, 3)])


def main() -> int:
    photo = load_photo()
    passed, failed = 0, 0

    def check(ok: bool, what: str) -> None:
        nonlocal passed, failed
        print(("  ok   " if ok else "  FAILED: ") + what)
        passed, failed = passed + (1 if ok else 0), failed + (0 if ok else 1)

    try:
        strip = render(photo, **{"overscan_mode": "strip"})
        letters = render(photo, **{"overscan_mode": "letters", "overscan_band": "1,1,1",
                                   "overscan_edge_color": "custom", "overscan_edge_ink": "0,0,0"})
        opened = True
        why = ""
    except Exception as e:  # the red: an engine that does not know the fields
        strip = letters = None
        opened, why = False, str(e)
    check(opened, f"the letters wire is accepted{'' if opened else ': ' + why}")
    if opened:
        sc = corners(strip)
        # The band's own colour, read where no lettering can reach: the same render with the
        # stock's name and the frame's number taken away (the print itself is checked below).
        common = {"overscan_mode": "letters", "overscan_band": "1,1,1",
                  "overscan_edge_color": "custom", "overscan_edge_ink": "0,0,0"}
        bare = render(photo, **common, **{"overscan_edge_text": "", "overscan_frame_number": 0,
                                          "overscan_edge_name": False, "overscan_edge_number": False,
                                          "overscan_edge_marks": False})
        # v2 (the owner's clarification, 2026-11-12): no band exists at all — the canvas is the
        # photo's own, and with the print switched off the render IS the picture.
        off = render(photo, **{"overscan_active": False})
        lh, lw, _ = bare.shape
        oh, ow, _ = off.shape
        check(abs(lh - oh) <= 2 and abs(lw - ow) <= 2,
              f"letters keeps the photo's own canvas: {lh} x {lw} against the frame's {oh} x {ow}")
        ch, cw = min(lh, oh), min(lw, ow)
        untouched = float(np.abs(bare[:ch, :cw] - off[:ch, :cw]).max())
        check(untouched < 0.02,
              f"with the print off, the picture is untouched (max delta {untouched:.4f})")

        def sides(out):
            """The bands on all four canvas edges: which edge the print lands on is the
            layout's business (a vertical strip puts it down the sides, a roll format
            across the top and bottom), so an element's pixel is looked for in any."""
            # From 8 px in (about a millimetre at either format's scale) — and the WHOLE
            # edge, not the middle of it: a print's marks sit where the film puts them,
            # corners included (120's numbers landed at the ends of this crop).
            return np.concatenate([out[8:112, :].reshape(-1, 3),
                                   out[-112:-8, :].reshape(-1, 3),
                                   out[:, 8:112].reshape(-1, 3),
                                   out[:, -112:-8].reshape(-1, 3)])

        full = render(photo, **common, **{"overscan_edge_text": "SPEKTRA 400",
                                          "overscan_edge_name": True, "overscan_edge_number": True,
                                          "overscan_edge_marks": True})
        name_off = render(photo, **common, **{"overscan_edge_text": "SPEKTRA 400",
                                              "overscan_edge_name": False, "overscan_edge_number": False,
                                              "overscan_edge_marks": False})
        dn = float(np.abs(sides(full) - sides(name_off)).max())
        check(dn > 0.1, f"overscan_edge_name takes the stock's row off (with/without delta {dn:.3f})")
        full = render(photo, **common, **{"overscan_frame_number": 12, "overscan_edge_text": "",
                                          "overscan_edge_name": False, "overscan_edge_number": True,
                                          "overscan_edge_marks": True})
        num_off = render(photo, **common, **{"overscan_frame_number": 12, "overscan_edge_text": "",
                                             "overscan_edge_name": False, "overscan_edge_number": False,
                                             "overscan_edge_marks": True})
        du = float(np.abs(sides(full) - sides(num_off)).max())
        check(du > 0.1, f"overscan_edge_number takes the frame's number off (delta {du:.3f})")
        full = render(photo, **common, **{"overscan_frame_number": 12, "overscan_edge_text": "",
                                          "overscan_edge_name": False, "overscan_edge_number": True,
                                          "overscan_edge_marks": False})
        mk_off = render(photo, **common, **{"overscan_frame_number": 12, "overscan_edge_text": "",
                                            "overscan_edge_name": False, "overscan_edge_number": True,
                                            "overscan_edge_marks": True})
        dm = float(np.abs(sides(full) - sides(mk_off)).max())
        check(dm > 0.1, f"overscan_edge_marks takes the arrows off (delta {dm:.3f})")

        # 120 (120_645): the same three switches on the roll format's own print. The engine
        # asks for the picture cut to the gate (56 x 41.5), so the frame is cut here first.
        common120 = dict(common, **{"overscan_format": "120_645"})
        ph, pw, _ = photo.shape
        aspect = 41.5 / 56.0                       # the gate's height / width
        photo120 = photo[:int(round(pw * aspect)), :] if ph / pw > aspect \
            else photo[:, :int(round(ph / aspect))]
        f_on = render(photo120, **common120, **{"overscan_edge_text": "SPEKTRA 400",
                                             "overscan_frame_number": 12, "overscan_edge_name": True,
                                             "overscan_edge_number": True, "overscan_edge_marks": True})
        all_off = render(photo120, **common120, **{"overscan_edge_text": "SPEKTRA 400",
                                               "overscan_frame_number": 12, "overscan_edge_name": False,
                                               "overscan_edge_number": False, "overscan_edge_marks": False})
        check(abs(f_on.shape[0] / f_on.shape[1] - 41.5 / 56.0) < 0.02,
              f"the 120 letters canvas keeps the gate's own shape ({f_on.shape[1]} x {f_on.shape[0]})")
        d120 = float(np.abs(sides(f_on) - sides(all_off)).max())
        check(d120 > 0.1, f"the 120 print answers the switches (with/off delta {d120:.3f})")
        num_off_120 = render(photo120, **common120, **{"overscan_frame_number": 12, "overscan_edge_text": "",
                                                   "overscan_edge_name": False, "overscan_edge_number": False,
                                                   "overscan_edge_marks": True})
        num_on_120 = render(photo120, **common120, **{"overscan_frame_number": 12, "overscan_edge_text": "",
                                                  "overscan_edge_name": False, "overscan_edge_number": True,
                                                  "overscan_edge_marks": True})
        d120n = float(np.abs(sides(num_on_120) - sides(num_off_120)).max())
        check(d120n > 0.1, f"the 120 frame number answers its switch (delta {d120n:.3f})")
        check(float(sc.mean()) < 0.15,
              f"strip mode still has its black rebate (corners mean {sc.mean():.4f})")
        # The picture itself, against the render with no overscan at all: strip carries a
        # scan's rotation and a film's margins and cannot match it pixel for pixel, but the
        # letters mode has no film, no registration and no band — it IS the picture.
        oh, ow, _ = off.shape
        hh, ww, _ = letters.shape
        gs = off[oh // 2 - 40:oh // 2 + 40, ow // 2 - 40:ow // 2 + 40]
        gl = letters[hh // 2 - 40:hh // 2 + 40, ww // 2 - 40:ww // 2 + 40]
        check(float(np.abs(gs - gl).max()) < 0.02,
              f"the letters mode holds the picture itself (max delta {np.abs(gs - gl).max():.4f})")
        # The film is vertical here: the band runs down the canvas' left and right sides.
        side = letters[hh // 6:5 * hh // 6, 8:96]
        ink = float(side.reshape(-1, 3).max(axis=1).min())
        check(ink < 0.35,
              f"the ink is at the photo's edge: the strip's darkest pixel reads {ink:.3f} (the custom near-black)")
        moved = float(np.abs(side - bare[hh // 6:5 * hh // 6, 8:96]).max())
        check(moved > 0.1,
              f"the lettering is on the band: with the words taken away the band moves by {moved:.3f}")

    print(f"edge letters checks: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
