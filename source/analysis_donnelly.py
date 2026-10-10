#!/usr/bin/env python3
"""Correct Donnelly's correction, and settle whether it is applicable to a hull.

The paper previously said Donnelly's correction "is not applicable here" because the
reference frame is a convex hull rather than a rectangle. That is wrong: the
correction needs only the window AREA and PERIMETER, both of which a convex polygon
has. What actually happened is that the earlier implementation was buggy — it
returned R climbing with n (4.5, 8.3, 11-16 on complete spatial randomness), which
is an unbounded term, not a correction.

Donnelly (1978) replaces the CSR expectation of the mean nearest-neighbour distance,
1/(2 sqrt(rho)), with its edge-corrected value

    E[d] ~ 1/(2 sqrt(N/A)) + (0.0514 + 0.041/sqrt(N)) * (P/N)

so the corrected index is R = dbar / E[d]. A correct implementation must tend to 1
on CSR at every n, and must not drift with n.

Writes: results_donnelly.json
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np
from scipy.spatial import ConvexHull, cKDTree

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analysis_common import load_years  # noqa: E402
from analysis_multiscale import locs_of, hull_edges  # noqa: E402

RNG = np.random.default_rng(20261003)


def mean_nn(P: np.ndarray) -> float:
    d, _ = cKDTree(P).query(P, k=2)
    return float(np.mean(d[:, 1]))


def R_raw(P: np.ndarray, A: float) -> float:
    return mean_nn(P) / (1.0 / (2.0 * math.sqrt(len(P) / A)))


def R_donnelly(P: np.ndarray, A: float, per: float) -> float:
    """The corrected form. Area AND perimeter, both available for a hull."""
    n = len(P)
    exp = 1.0 / (2.0 * math.sqrt(n / A)) + (0.0514 + 0.041 / math.sqrt(n)) * (per / n)
    return mean_nn(P) / exp


def hull_area_perimeter(poly: np.ndarray) -> tuple[float, float]:
    """Area and perimeter of a convex polygon given its vertices in order."""
    a = 0.0
    p = 0.0
    m = len(poly)
    for i in range(m):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % m]
        a += x1 * y2 - x2 * y1
        p += math.hypot(x2 - x1, y2 - y1)
    return abs(a) / 2.0, p


def sample_in_hull(n: int, poly: np.ndarray, rng) -> np.ndarray:
    x0, y0 = poly.min(axis=0)
    x1, y1 = poly.max(axis=0)
    out = []
    while len(out) < n:
        c = np.column_stack([rng.uniform(x0, x1, 4 * n), rng.uniform(y0, y1, 4 * n)])
        h = ConvexHull(poly)
        # inside test via half-plane signs using the hull equations
        inside = np.ones(len(c), bool)
        for eq in h.equations:
            inside &= (c @ eq[:2] + eq[2]) <= 0
        out.extend(c[inside].tolist())
    return np.array(out[:n])


def main() -> int:
    here = pathlib.Path(__file__).resolve().parent
    idx = json.loads((here / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)

    allP = np.vstack([locs_of(yrs[y]) for y in years])
    poly, A = hull_edges(allP)
    per = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        per += math.hypot(x2 - x1, y2 - y1)
    print("study hull: area %.0f km2, perimeter %.0f km" % (A / 1e6, per / 1000.0))
    print()

    res: dict = {"hull_area_km2": A / 1e6, "hull_perimeter_km": per / 1000.0}

    # ---- known-answer control on CSR inside the actual hull ------------------
    print("CONTROL: complete spatial randomness inside the hull (true R = 1)")
    print("     n   R_raw   R_Donnelly")
    ctl = []
    for n in (50, 100, 200, 500, 1000, 2000):
        Rs, Rd = [], []
        for _ in range(20):
            P = sample_in_hull(n, poly, RNG)
            Rs.append(R_raw(P, A))
            Rd.append(R_donnelly(P, A, per))
        ctl.append({"n": n, "R_raw": float(np.mean(Rs)), "R_raw_sd": float(np.std(Rs)),
                    "R_donnelly": float(np.mean(Rd)), "R_donnelly_sd": float(np.std(Rd))})
        print("  %5d  %.3f   %.3f" % (n, np.mean(Rs), np.mean(Rd)))
    res["csr_control"] = ctl

    # does the corrected term drift with n? that was the earlier bug
    drift = max(abs(c["R_donnelly"] - 1.0) for c in ctl)
    res["donnelly_max_abs_dev_from_1"] = float(drift)
    print()
    print("  max |R_Donnelly - 1| over all n: %.3f  -> %s"
          % (drift, "bounded, correction is valid" if drift < 0.25
             else "STILL DRIFTS, implementation wrong"))
    print()

    # ---- apply to the real series -------------------------------------------
    print("APPLIED: the real network, raw and corrected")
    rows = []
    for y in years:
        P = locs_of(yrs[y])
        rows.append({"year": y, "n": int(len(P)),
                     "R_raw": R_raw(P, A), "R_donnelly": R_donnelly(P, A, per)})
        print("  %d n=%-4d  raw %.3f   donnelly %.3f"
              % (y, len(P), rows[-1]["R_raw"], rows[-1]["R_donnelly"]))
    res["series"] = rows
    res["endpoint_raw"] = rows[0]["R_raw"] - rows[-1]["R_raw"]
    res["endpoint_donnelly"] = rows[0]["R_donnelly"] - rows[-1]["R_donnelly"]
    print()
    print("  fall, raw      : %.3f -> %.3f" % (rows[0]["R_raw"], rows[-1]["R_raw"]))
    print("  fall, corrected: %.3f -> %.3f"
          % (rows[0]["R_donnelly"], rows[-1]["R_donnelly"]))

    json.dump(res, open(here / "results_donnelly.json", "w"), indent=1)
    print("\nwrote results_donnelly.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
