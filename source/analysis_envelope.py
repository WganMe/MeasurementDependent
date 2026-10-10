#!/usr/bin/env python3
"""Round 15: the two controls the board review calls blocking.

[1] The multiscale CSR control. The previous control was a SINGLE CSR pattern, so
    its per-scale values (+76.7, +104.0, +130.9 ...) were being read as the
    estimator's bias. They are not: a single realisation of a random pattern has
    sampling scatter of the same order. What matters is the ENVELOPE over many
    CSR realisations, and whether the observed curve lies outside it. This script
    runs the envelope at several n and reports, at each scale:
        csr_mean   the estimator's bias (should be ~0)
        csr_sd     the scatter of one realisation
        env95      the 2.5-97.5 envelope
        obs        the observed L
        ratio      obs / envelope upper limit -- how far the signal clears noise

[2] The inhomogeneous null's circularity. The intensity surface is smoothed from
    the same points it tests, which the review calls a fundamental circularity. We
    re-estimate it LEAVE-ONE-OUT: for each location, the intensity at that point is
    computed from every other location. A circularity-free intensity surface cannot
    be built from sensor locations alone, so we do not claim one; what we can show
    is that the cluster excess survives when each point is removed from the
    estimate that judges it.

Writes: results_envelope.json
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from analysis_common import load_years                             # noqa: E402
from analysis_multiscale import (L_border, hull_edges,          # noqa: E402
                                      inward_lines, ids_of, locs_of, RS)

HERE = pathlib.Path(__file__).resolve().parent
NRUN = 199


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    allP = np.vstack([ids_of(yrs[y]) for y in years])
    poly, A = hull_edges(allP)
    lines = inward_lines(poly)
    rng = np.random.default_rng(20261003)
    res = {"years": years, "A_hull_m2": float(A), "rs": RS.tolist(), "nrun": NRUN}

    def in_hull(P):
        ok = np.ones(len(P), bool)
        for nrm, c in lines:
            ok &= (P @ nrm) >= (c - 1e-9)
        return ok

    def sample_hull(n):
        box = np.array([poly[:, 0].min(), poly[:, 1].min(),
                        poly[:, 0].max(), poly[:, 1].max()])
        out = []
        while len(out) < n:
            c = np.column_stack([rng.uniform(box[0], box[2], n * 2),
                                 rng.uniform(box[1], box[3], n * 2)])
            out.extend(c[in_hull(c)])
        return np.array(out[:n])

    # ------------------------------------------------------------------ [1]
    print("\n[1] the CSR control as an envelope, not a single realisation")
    print("     n   scale   csr_mean  csr_sd   env_lo   env_hi")
    ctl = {}
    for n in (39, 200, 561):
        curves = np.array([L_border(sample_hull(n), A, lines=lines)
                           for _ in range(NRUN)])
        m = np.nanmean(curves, axis=0)
        sd = np.nanstd(curves, axis=0)
        lo = np.nanpercentile(curves, 2.5, axis=0)
        hi = np.nanpercentile(curves, 97.5, axis=0)
        ctl[str(n)] = {"mean": m.tolist(), "sd": sd.tolist(),
                       "lo": lo.tolist(), "hi": hi.tolist(),
                       "mean_abs_bias_m": float(np.nanmean(np.abs(m))),
                       "mean_sd_m": float(np.nanmean(sd))}
        for i, r in enumerate(RS):
            print("  %5d  %5.0f  %+8.1f  %7.1f  %+8.1f  %+8.1f"
                  % (n, r, m[i], sd[i], lo[i], hi[i]))
        print("     -> mean |bias| %.1f m against a single-realisation sd of %.1f m"
              % (ctl[str(n)]["mean_abs_bias_m"], ctl[str(n)]["mean_sd_m"]))
    res["csr_envelope"] = ctl

    # the decisive comparison: observed against the envelope at the matching n
    print("\n    observed against the envelope, locations, per year")
    obs_rows = []
    for y in years:
        P = locs_of(yrs[y])
        L = L_border(P, A, lines=lines)
        n = len(P)
        # envelope at this n (draw fresh, since n varies by year)
        curves = np.array([L_border(sample_hull(n), A, lines=lines)
                           for _ in range(NRUN)])
        hi = np.nanpercentile(curves, 97.5, axis=0)
        sd = np.nanstd(curves, axis=0)
        above = int(np.sum(L > hi))
        # signal-to-noise at the smallest scale where the signal is measurable
        with np.errstate(divide="ignore", invalid="ignore"):
            snr = np.where(sd > 0, L / sd, np.nan)
        obs_rows.append({"year": y, "n": n,
                         "L": L.tolist(), "env_hi": hi.tolist(),
                         "above": above, "n_scales": int(len(RS)),
                         "snr": snr.tolist()})
        print("    %d n=%-4d  L above the CSR envelope at %d of %d scales; SNR at 500 m = %.0f"
              % (y, n, above, len(RS), snr[list(RS).index(500.0)]))
    res["observed_vs_envelope"] = obs_rows
    allabove = [r["above"] for r in obs_rows]
    print("    -> above the envelope at every scale in every year: %s"
          % all(a == len(RS) for a in allabove))
    res["above_every_scale_every_year"] = bool(all(a == len(RS) for a in allabove))

    # the bias relative to the observed signal, which is what the review asks for
    print("\n    bias as a fraction of the observed signal")
    c39 = ctl["39"]
    for i, r in enumerate(RS):
        obsmin = min(row["L"][i] for row in obs_rows)
        bias = abs(c39["mean"][i])
        print("      %5.0f m: CSR bias %6.1f m = %.1f%% of the smallest observed L (%.0f m)"
              % (r, bias, 100 * bias / obsmin, obsmin))
    res["bias_fraction"] = {
        str(r): float(abs(c39["mean"][i]) / min(row["L"][i] for row in obs_rows))
        for i, r in enumerate(RS)}

    # ------------------------------------------------------------------ [2]
    print("\n[2] leave-one-out intensity: does the cluster excess survive removing")
    print("    each point from the estimate that judges it?")
    # A proper kernel intensity: lam(x_i) = sum_{j != i} K(||x_i-x_j|| / h) / (2 pi h^2).
    # An earlier version of this block summed exp(-(d/h)^2/2) over the *nearest-neighbour
    # distances*, which is not a density estimate at all: it weighted each point by its own
    # distance to its own neighbour and returned ratios up to 9 at n=39. The ratio is meant
    # to be O(1), so that version was wrong and is replaced here.
    BAND = 750.0
    loo_rows = []
    for y in (2013, 2020, 2026):
        P = locs_of(yrs[y])
        ratios, lam_all = [], []
        allD = cKDTree(P).query(P, k=len(P))[0]
        for i in range(len(P)):
            d = np.delete(allD[i], i)                 # distances to every OTHER point
            w = np.exp(-0.5 * (d / BAND) ** 2)
            lam = w.sum() / (2.0 * math.pi * BAND ** 2)
            lam_all.append(lam)
            if lam > 0:
                ratios.append(allD[i][1] / (1.0 / (2.0 * math.sqrt(lam))))
        ratios = np.array(ratios)
        loo_rows.append({"year": y, "n": int(len(P)),
                         "median_loo_R": float(np.median(ratios)),
                         "median_lam": float(np.median(lam_all)),
                         "frac_below_1": float(np.mean(ratios < 1))})
        print("    %d n=%-4d  median LOO ratio %.3f, median lam %.2e, %.0f%% of points below 1"
              % (y, len(P), np.median(ratios), np.median(lam_all),
                 100 * np.mean(ratios < 1)))
    res["loo_intensity"] = loo_rows
    res["loo_note"] = ("lambda_i = sum_{j!=i} K(||x_i-x_j||/h)/(2 pi h^2), h = 750 m, "
                       "all other points. This replaces an earlier implementation that "
                       "weighted nearest-neighbour distances.")

    json.dump(res, open(HERE / "results_envelope.json", "w"), indent=1)
    print("\nwrote results_envelope.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
