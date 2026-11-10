// finish.metal -- the finish path's two pointwise kernels.
//
// The finish path takes the frame as the *finished* picture: a photograph
// already graded elsewhere, handed to the engine for what only the engine
// makes -- film grain at the image's own density, and the film edge and date.
// No film and no paper: the colour enters and leaves as the same values.
//
// Grain lives on a density axis (the sub-layer model reads the stock's own
// normalised curves), so the picture is read onto one and back:
//
//     n   = -log10(max(rgb, kFloor)) / dmax      per channel, the stock's dmax
//     rgb = 10^(-n * dmax)
//
// The two are inverses in real arithmetic, so with grain off and no edge the
// path is the identity, to float32 storage -- which is what
// `tests/finish_checks.py` holds it to.
//
// `n` is **deliberately not clamped**: a pixel darker than the stock's dmax, or
// brighter than density 0, looks up the nearest end of the grain curve exactly
// as a negative at the top of its curve does, and the inverse still returns the
// value that went in. Clamping here would lift the blacks and change the
// picture the path promises not to change.
#include "spk_common.h"

// Straight through the stock's density range: `dmax` is (3) floats.
kernel void spk_finish_to_density(device const float* rgb [[buffer(0)]],
                                  device const float* dmax [[buffer(1)]],
                                  device const uint* meta [[buffer(2)]],
                                  device float* out [[buffer(3)]],
                                  uint3 thread_position_in_grid [[thread_position_in_grid]]) {
    uint i = thread_position_in_grid.x;
    if (i >= meta[0]) return;
    for (uint ch = 0u; ch < 3u; ++ch) {
        float v = rgb[3u * i + ch];
        // Below this a pixel is black: the density would be infinite and the
        // inverse would still give 1e-9 back, not 0. See the header.
        float d = -log10(max(v, 1e-9f));
        out[3u * i + ch] = d / max(dmax[ch], 1e-6f);
    }
}

// And back, after the grain node has added its own density.
kernel void spk_finish_from_density(device const float* n [[buffer(0)]],
                                    device const float* dmax [[buffer(1)]],
                                    device const uint* meta [[buffer(2)]],
                                    device float* out [[buffer(3)]],
                                    uint3 thread_position_in_grid [[thread_position_in_grid]]) {
    uint i = thread_position_in_grid.x;
    if (i >= meta[0]) return;
    for (uint ch = 0u; ch < 3u; ++ch) {
        float d = n[3u * i + ch] * max(dmax[ch], 1e-6f);
        out[3u * i + ch] = pow(10.0f, -d);
    }
}
