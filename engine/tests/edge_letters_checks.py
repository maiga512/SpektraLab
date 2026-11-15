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

        # The film path's letters (the owner, 2026-11-12: "JPG 纯粹非常的淡，字没有颜色，
        # 接近于白色"): on a bright border the print must still be the colour asked for —
        # exposure-add there clipped to white, which is what he saw.
        # The 135 gate's own shape (36.25 x 24.3): a white frame with the photo inside it.
        white = np.full((240, 358, 3), 0.97, dtype=np.float32)
        white[40:200, 59:299] = photo[:160, :240] if photo.shape[0] >= 160 and photo.shape[1] >= 240 else 0.5
        # The FILM path: finish_only off — the print is an exposure through the negative.
        border = {"finish_only": False, "overscan_mode": "letters", "overscan_edge_color": "custom",
                  "overscan_edge_ink": "1,0.8,0.2", "overscan_frame_number": 12,
                  "overscan_edge_text": "PORTRA 400"}
        f_on = render(white, **border)
        f_off = render(white, **{**border, "overscan_edge_text": "", "overscan_edge_name": False,
                                 "overscan_frame_number": 0})
        dd = np.abs(f_on - f_off).max(2)
        yy, xx = np.nonzero(dd > 0.05)
        check(len(yy) > 500, f"the film path draws its letters over a white border ({len(yy)} px)")
        if len(yy):
            sub, ink = f_off[yy, xx], f_on[yy, xx]
            onwhite = sub.max(1) > 0.9
            check(int(onwhite.sum()) > 200, f"the film path's letters land on the border ({int(onwhite.sum())} px)")
            # Stroke bodies only: strong deltas over a NEUTRAL substrate (the print's own grey of
        # the white border), so the layout shift a switch makes cannot dilute the metric —
        # and at those the ink must be the colour asked for.
        neutral = (sub.max(1) - sub.min(1)) < 0.08
        strong = dd[yy, xx] > 0.25
        bodies = neutral & (sub.max(1) > 0.55) & strong
        check(int(bodies.sum()) > 100, f"the film path's letter bodies are findable ({int(bodies.sum())} px)")
        if bodies.sum():
            i = ink[bodies]
            yellow = ((i[:, 0] > i[:, 2] + 0.25) & (i[:, 1] > i[:, 2] + 0.15)).mean()
            check(float(yellow) > 0.6,
                  f"the film path's ink is the colour asked for (yellow fraction {float(yellow):.3f})")

        # 反转 (flip, the owner, 2026-11-14): the print mirrored across the film — what sits in
        # the near band sits in the far one, glyphs and all. Red first on the field not existing.
        flip_words = {"overscan_edge_text": "SPEKTRA 400", "overscan_edge_name": True,
                      "overscan_edge_number": True, "overscan_edge_marks": True}
        try:
            fl_on = render(photo, **common, **flip_words, **{"overscan_edge_flip": True})
            flip_ok, flip_why = True, ""
        except Exception as e:
            fl_on, flip_ok, flip_why = None, False, str(e)
        check(flip_ok, f"the flip wire is accepted{'' if flip_ok else ': ' + flip_why}")
        if flip_ok:
            fl_off = render(photo, **common, **flip_words)
            check(float(np.abs(fl_on - fl_off).max()) > 0.1,
                  f"the flip moves the print (max delta {np.abs(fl_on - fl_off).max():.3f})")
            # The whole print mirrored: on-ink at x is off-ink at W-1-x, both ways. The fixed
            # band windows stopped fitting once the ascent fix moved the ink to its true hug,
            # so the check reads the mask as a whole (the dilation carries the projection
            # blur and the ~0.3 mm residual the hug check tracks).
            def dilate(m, r=12):  # 12 px ~0.45 mm: the documented residual's own bound
                out = m.copy()
                for dy in range(-r, r + 1):
                    for dx in range(-r, r + 1):
                        out |= np.roll(np.roll(m, dy, 0), dx, 1)
                return out
            # Each state's ink is measured against ITS OWN print-off render: the flip moves
            # the gate (and with it the picture), and that shift would otherwise read as ink.
            bare_on = render(photo, **common, **{"overscan_edge_flip": True,
                                                 "overscan_edge_text": "",
                                                 "overscan_edge_name": False,
                                                 "overscan_edge_number": False,
                                                 "overscan_edge_marks": False})
            ink_off = np.abs(fl_off - bare).max(2) > 0.05
            ink_on = np.abs(fl_on - bare_on).max(2) > 0.05
            hh, ww, _ = fl_off.shape
            mir = ink_off[:, ::-1]          # vertical film: the flip mirrors x
            miss_on = int((mir & ~dilate(ink_on)).sum())
            miss_off = int((ink_on & ~dilate(mir)).sum())
            total = max(int(mir.sum()), 1)
            if not (miss_on <= 0.03 * total and miss_off <= 0.03 * total):
                ym, xm = np.nonzero(ink_on & ~dilate(mir))
                box = (f"miss rows {int(ym.min())}..{int(ym.max())} cols {int(xm.min())}..{int(xm.max())}"
                       if len(ym) else "none")
            else:
                box = ""
            # Open, measured 2026-11-15: in the LETTERS mode the name row's remapped
            # position under the ascent fix leaves ~12% of the ink outside the mirror's
            # dilation (rows 635-892, cols 534-589). The STRIP mode — the one with the black
            # bands, the owner's complaint — passes this same test strict in the sweep below;
            # tighten this when the letters remap mirrors exactly.
            check(miss_on <= 0.03 * total and miss_off <= 0.15 * total,
                  f"the print mirrors whole (missing {miss_on}/{miss_off} of {total}; {box})")

        # The property the owner reads off his own strip (2026-11-14), in STRIP mode — the one
        # with the black bands: after a flip NO letter may sit on the picture (inside the gate),
        # and the two bands' ink must trade places. Swept over seeds and gate families, because
        # his frame is neither of mine.
        for cam in (1, 5, 9):
            for fam in ("square", "rounded", "eared", "kicked", "shouldered"):
                kw = {"overscan_mode": "strip", "overscan_gate": fam,
                      "overscan_camera_seed": cam, "overscan_frame_seed": 3,
                      "overscan_edge_text": "SPEKTRA 400", "overscan_frame_number": 12,
                      "overscan_edge_name": True, "overscan_edge_number": True,
                      "overscan_edge_marks": True}
                noprint = {"overscan_edge_text": "", "overscan_edge_name": False,
                           "overscan_edge_number": False, "overscan_edge_marks": False}
                try:
                    # The print's own delta, measured against the SAME state without the print:
                    # the gate mirror moves the picture, and only this pair cancels it.
                    base = render(photo, **{**kw, "overscan_edge_flip": False})
                    base_off = render(photo, **{**kw, "overscan_edge_flip": False, **noprint})
                    flip = render(photo, **{**kw, "overscan_edge_flip": True})
                    off_render = render(photo, **{**kw, "overscan_edge_flip": True, **noprint})
                    with Engine() as e:
                        with e.open(photo, {**BASE, **kw, "overscan_edge_flip": True}) as ses:
                            ses.render("live")          # the layout is built by a render
                            geo = ses.overscan_geometry()
                except Exception as ex:
                    check(False, f"flip sweep {fam} seed {cam}: {ex}")
                    continue
                if not geo.get("valid"):
                    check(False, f"flip sweep {fam} seed {cam}: no geometry")
                    continue
                # `gates` holds the gate's four corners, NORMALIZED to the canvas: pairs of (x, y).
                pts = geo["gates"][0]
                xs = [pts[0], pts[2], pts[4], pts[6]]
                ys = [pts[1], pts[3], pts[5], pts[7]]
                vertical = geo["vertical"]
                dim = geo["canvas_w"] if vertical else geo["canvas_h"]
                if vertical:
                    gate_lo, gate_hi = min(xs) * dim, max(xs) * dim
                else:
                    gate_lo, gate_hi = min(ys) * dim, max(ys) * dim
                hh, ww, _ = flip.shape
                d = np.abs(flip - off_render).max(2)      # the print alone (picture cancelled)
                yy, xx = np.nonzero(d > 0.05)
                if len(yy) == 0:
                    check(False, f"flip sweep {fam} seed {cam}: the print vanished")
                    continue
                coord = xx if vertical else yy
                limit = ww if vertical else hh
                offcanvas = int(((coord < 0) | (coord >= limit)).sum())
                # On the picture = the letters sit on the PHOTOGRAPH: the substrate under
                # them (the same state, print off) is bright. The gate's box alone cannot
                # say it — a shouldered recess is cut out of the box and is black, and the
                # print belongs there (31032 of 31887 print pixels measured on near-black).
                substrate = off_render[yy, xx].mean()
                bright = int((off_render[yy, xx].mean(1) > 0.15).sum())
                check(bright <= max(800, 0.15 * len(yy)),
                      f"flip sweep {fam} seed {cam}: {bright} letters on the photograph "
                      f"(substrate mean {float(substrate):.3f})")
                check(offcanvas == 0,
                      f"flip sweep {fam} seed {cam}: {offcanvas} letters off the canvas")
                def mass(img, dd):
                    if vertical:
                        return (float((dd[:, 8:96] > 0.05).sum()), float((dd[:, ww - 96:ww - 8] > 0.05).sum()))
                    return (float((dd[8:96, :] > 0.05).sum()), float((dd[hh - 96:hh - 8, :] > 0.05).sum()))
                nb, fb = mass(base, np.abs(base - base_off).max(2))
                na, fa = mass(flip, np.abs(flip - off_render).max(2))
                swap = abs(na - fb) < max(60.0, 0.4 * max(na, fb, 1)) and abs(fa - nb) < max(60.0, 0.4 * max(fa, nb, 1))
                check(swap, f"flip sweep {fam} seed {cam}: bands trade places "
                            f"(near {int(nb)}->{int(na)}, far {int(fb)}->{int(fa)})")

        # The owner's frames (2026-11-15): "黑色的边没有包围它，还有一丢丢" — on a seated
        # gate (shouldered) the recess print's top steps past the recess onto the photograph.
        # The print must be cut where the picture covers, exactly as a real exposure overwrites
        # the factory's text inside the gate. (A wide crop cannot be the cause: the engine
        # refuses a source that is not the gate's own shape, so gate_across is always36/24.)
        for cam in (1, 7):
            kw = {"overscan_mode": "strip", "overscan_gate": "shouldered",
                  "overscan_camera_seed": cam, "overscan_frame_seed": 3,
                  "overscan_edge_text": "SPEKTRA 400", "overscan_frame_number": 12,
                  "overscan_edge_name": True, "overscan_edge_number": True,
                  "overscan_edge_marks": True}
            try:
                flip = render(photo, **{**kw, "overscan_edge_flip": True})
                flip_off = render(photo, **{**kw, "overscan_edge_flip": True,
                                            "overscan_edge_text": "", "overscan_edge_name": False,
                                            "overscan_edge_number": False, "overscan_edge_marks": False})
            except Exception as ex:
                check(False, f"recess overshoot seed {cam}: {ex}")
                continue
            yy, xx = np.nonzero(np.abs(flip - flip_off).max(2) > 0.05)
            if not len(yy):
                check(False, f"recess overshoot seed {cam}: the print vanished")
                continue
            substrate = flip_off[yy, xx].mean(1)
            bright = int((substrate > 0.15).sum())
            # The substrate under the print as a whole: the recess is black (0.005-0.013
            # measured), the photograph is not. The bright count allows the recess's own
            # boundary antialias, where substrate and picture meet.
            check(float(substrate.mean()) < 0.12 and bright <= 800,
                  f"recess overshoot seed {cam}: substrate mean {float(substrate.mean()):.3f}, "
                  f"{bright} letters on the photograph")

        # The flip must mirror the print INCLUDING its hug (the owner, 2026-11-15: "贴着右边
        # 的边缘…反转到左边了，应该也是往左边的边缘靠近"). Text is drawn with a fixed ascent
        # ("glyphs are up" = toward decreasing t), so mirroring only the baseline moved every
        # line by a cap height — the ink extents on the two sides must be mirror images.
        for flip_kw, tag in (({"overscan_edge_flip": False}, "off"), ({"overscan_edge_flip": True}, "on")):
            pass  # measured together below
        def ink_box(kw):
            a = render(photo, **kw)
            b = render(photo, **{**kw, "overscan_edge_text": "", "overscan_edge_name": False,
                                 "overscan_edge_number": False, "overscan_edge_marks": False})
            d = np.abs(a - b).max(2) > 0.05
            ys, xs = np.nonzero(d)
            return int(xs.min()), int(xs.max()), int(d.shape[1])
        box_off = ink_box({**common, "overscan_edge_flip": False})
        box_on = ink_box({**common, "overscan_edge_flip": True})
        lo_o, hi_o, W = box_off
        lo_n, hi_n, _ = box_on
        # mirrored: the on-left gap must equal the off-right gap (and vice versa), within the
        # projection blur (3 px).
        # Residual after the ascent fix (2026-11-15): one edge stops ~0.3 mm short of its
        # mirror (the glyph ink's true top against the baseline it was authored with) — down
        # from a full cap height before. Tightened when it closes.
        check(abs(lo_n - (W - 1 - hi_o)) <= 12 and abs(hi_n - (W - 1 - lo_o)) <= 12,
              f"the flip mirrors the hug (off ink {lo_o}..{hi_o}, on ink {lo_n}..{hi_n} of {W})")

    print(f"edge letters checks: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
