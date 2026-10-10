#!/usr/bin/env python3
"""Round 17: do R and L agree, once a thinning-invariant statistic is used?

The board review makes the sharpest methodological point of the round. R (a
nearest-neighbour ratio) is NOT invariant under random thinning; K and L are. On a
fixed clustered structure, adding points lowers the MEAN NEAREST-NEIGHBOUR DISTANCE
mechanically -- two points can share one neighbour -- and R is built from that mean.
So a falling R is compatible with a constant or even weakening second-order
clustering, and the paper's Figure 2 caption ("clustering strengthened") is not
supported by the figure if L falls at the same time.

This script tests the objection directly:

  1. On a KNOWN fixed clustered pattern, thin it progressively and watch R fall while
     L stays put. That is the mechanism, demonstrated rather than asserted.
  2. On the REAL network, ask whether the observed R fall is more than the thinning
     effect accounts for, by comparing each year's R against the R of a thinned
     version of the 2026 pattern at the same n, on the same hull.
  3. Report L at a fixed scale on the same thinned sets, since L is the invariant.

If the real R falls faster than thinning predicts, the fall is not a size artefact.
If it does not, the paper's headline is a size artefact and must be reported as one.

Writes: results_thinning.json
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analysis_common import load_years  # noqa: E402
from analysis_multiscale import (  # noqa: E402
    locs_of, hull_edges, inward_lines, L_border,
)

RNG = np.random.default_rng(20261003)


def R_of(P: np.ndarray, A: float) -> float:
    d, _ = cKDTree(P).query(P, k=2)
    return float(np.mean(d[:, 1])) / (1.0 / (2.0 * math.sqrt(len(P) / A)))


def main() -> int:
    here = pathlib.Path(__file__).resolve().parent
    idx = json.loads((here / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)

    allP = np.vstack([locs_of(yrs[y]) for y in years])
    poly, A = hull_edges(allP)
    lines = inward_lines(poly)
    res: dict = {"hull_area_m2": A}

    # ---- 1. the mechanism, on a fixed clustered pattern ----------------------
    print("[1] the thinning mechanism on a FIXED clustered pattern")
    print("    Two Thomas-like clusters, never moved; only n changes by thinning.")
    centres = np.array([[0.0, 0.0], [3000.0, 2000.0]])
    big = []
    for c in centres:
        big.append(c + RNG.normal(0, 250.0, size=(4000, 2)))
    big = np.vstack(big)
    print("     n     R      L(1km)")
    mech = []
    for n in (4000, 2000, 1000, 500, 250):
        sub = big[RNG.choice(len(big), n, replace=False)]
        r = R_of(sub, A)
        Lv = L_border(sub, A, lines=lines, rs=[1000.0])
        mech.append({"n": n, "R": r, "L_1km": float(Lv[0])})
        print("  %5d  %.3f  %8.1f" % (n, r, Lv[0]))
    res["mechanism"] = mech
    print()

    # ---- 2. the real network against a thinned reference ---------------------
    # Reference = the 2026 pattern (the densest). Thinning it to each year's n
    # gives the R that year's SIZE alone predicts on the CURRENT structure.
    print("[2] real network vs a thinned 2026 reference")
    print("    If observed R sits BELOW the thinned reference, the structure changed.")
    ref = locs_of(yrs[2026])
    rows = []
    print("  year    n   R observed   R thinned-2026 (mean +/- sd)   excess")
    for y in years:
        P = locs_of(yrs[y])
        n = len(P)
        if n >= len(ref):
            Rs = [R_of(ref, A)]
            sd = 0.0
        else:
            draws = [R_of(ref[RNG.choice(len(ref), n, replace=False)], A)
                     for _ in range(200)]
            Rs, sd = [float(np.mean(draws))], float(np.std(draws))
        obs = R_of(P, A)
        excess = obs - Rs[0]
        rows.append({"year": y, "n": n, "R_obs": obs,
                     "R_thinned_ref": Rs[0], "sd": sd, "excess": excess})
        print("  %4d %5d      %.3f            %.3f +/- %.3f          %+.3f"
              % (y, n, obs, Rs[0], sd, excess))
    res["vs_thinned_2026"] = rows
    print()
    e13 = rows[0]["excess"]
    e26 = rows[-1]["excess"]
    print("  excess in 2013: %+.3f   in 2026: %+.3f" % (e13, e26))
    print("  the fall in R beyond what size alone predicts: %.3f"
          % (e13 - e26))
    print("  NOTE: at n=561 the reference IS the 2026 pattern, so the 2026 row is")
    print("        vacuous (excess 0 by construction). Only the small-n rows carry")
    print("        information, and this reference cannot judge the densest year.")
    print()

    # ---- 2b. the pooled reference, which CAN judge every year ---------------
    # The thinned-2026 reference is self-referential at the largest n, so a
    # second reference is needed: the pooled set of distinct locations from all
    # fourteen years. Every year, including 2026, is then compared against a
    # structure it is a proper subset of. This was run inline once and never
    # stored; the paper originally quoted it with no result file
    # behind it, so it is computed and saved here.
    print("[2b] against the POOLED reference (1567 distinct sites), every year")
    pooled = np.unique(np.round(allP, 1), axis=0)
    print("  year    n   R observed   R pooled ref (mean +/- sd)      z")
    prow = []
    for y in years:
        P = locs_of(yrs[y])
        n = len(P)
        if n >= len(pooled):
            continue
        draws = np.array([R_of(pooled[RNG.choice(len(pooled), n, replace=False)], A)
                          for _ in range(400)])
        obs = R_of(P, A)
        z = (obs - draws.mean()) / draws.std()
        prow.append({"year": y, "n": n, "R_obs": obs,
                     "R_pooled": float(draws.mean()), "sd": float(draws.std()),
                     "z": float(z)})
        print("  %4d %5d      %.3f            %.3f +/- %.3f       %+.2f"
              % (y, n, obs, draws.mean(), draws.std(), z))
    res["vs_pooled"] = prow
    res["pooled_n_sites"] = int(len(pooled))
    print()

    # ---- 3. L at a fixed scale on the real years -----------------------------
    print("[3] the thinning-invariant side: L(1km) on the real years")
    print("  year    L(1km)")
    Lrows = []
    for y in years:
        P = locs_of(yrs[y])
        Lv = L_border(P, A, lines=lines, rs=[1000.0])
        Lrows.append({"year": y, "L_1km": float(Lv[0])})
        print("  %4d  %9.1f" % (y, Lv[0]))
    res["L_series_1km"] = Lrows
    print()
    print("  L(1km) 2013 -> 2026: %.1f -> %.1f  (%.0f%% change)"
          % (Lrows[0]["L_1km"], Lrows[-1]["L_1km"],
             100 * (Lrows[-1]["L_1km"] - Lrows[0]["L_1km"]) / Lrows[0]["L_1km"]))

    json.dump(res, open(here / "results_thinning.json", "w"), indent=1)
    print("\nwrote results_thinning.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
