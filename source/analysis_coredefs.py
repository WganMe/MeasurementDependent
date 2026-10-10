#!/usr/bin/env python3
"""Round 16b: is the core-rectangle result a modifiable areal unit artefact?

The 5--95\% symmetric core rectangle is an arbitrary support choice. If the
clustering result reverses or vanishes under other reasonable cores, the core
panel of the frame table is reporting the choice of percentile rather than the
network. This sweeps the percentile and also substitutes two non-rectangular
cores (a convex hull of the central points, and a fixed-radius disc about the
median centre) so the sensitivity is not confined to rectangles.

Writes: results_coredefs.json
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analysis_common import load_years, ols_hac, proj  # noqa: E402
from analysis_multiscale import locs_of  # noqa: E402


def _fit(years, R):
    """OLS slope and p on year, using the same routine as the headline."""
    yr = np.array(years, float)
    X = np.column_stack([np.ones_like(yr), yr])
    beta, se, r2, resid = ols_hac(R, X, 2)
    return {"slope": float(beta[1]), "ols_p": float(2 * _t_sf(abs(beta[1] / se[1]), len(yr) - 2))}


def _t_sf(t, df):
    from scipy import stats
    return stats.t.sf(t, df)


def ce_plain(Q: np.ndarray, A: float) -> float:
    """Clark--Evans R on a point set with reference area A, uncorrected."""
    from scipy.spatial import cKDTree
    if len(Q) < 2:
        return float("nan")
    d, _ = cKDTree(Q).query(Q, k=2)
    nn = d[:, 1]
    rho = len(Q) / A
    return float(np.mean(nn)) / (1.0 / (2.0 * math.sqrt(rho)))


def main() -> int:
    here = pathlib.Path(__file__).resolve().parent
    idx = json.loads((here / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)

    res: dict = {"years": years, "sweeps": {}}

    for pct in (1, 2.5, 5, 10, 25):
        rows = []
        for y in years:
            P = np.asarray(locs_of(yrs[y]), float)
            lo = np.percentile(P, pct, axis=0)
            hi = np.percentile(P, 100 - pct, axis=0)
            m = ((P[:, 0] >= lo[0]) & (P[:, 0] <= hi[0])
                 & (P[:, 1] >= lo[1]) & (P[:, 1] <= hi[1]))
            Q = P[m]
            A = (hi[0] - lo[0]) * (hi[1] - lo[1])
            rows.append({"year": y, "n": int(m.sum()), "A_km2": A / 1e6,
                         "R": ce_plain(Q, A)})
        R = np.array([r["R"] for r in rows])
        n = np.array([r["n"] for r in rows])
        fit = _fit(years, R)
        res["sweeps"]["trim_p%g" % pct] = {
            "pct": pct,
            "R_first": float(R[0]), "R_last": float(R[-1]),
            "slope": float(fit["slope"]),
            "p": float(fit["ols_p"]),
            "n_min": int(n.min()), "n_max": int(n.max()),
        }

    # convex hull of the central 80% of points (non-rectangular core)
    from scipy.spatial import ConvexHull
    rows = []
    for y in years:
        P = np.asarray(locs_of(yrs[y]), float)
        lo = np.percentile(P, 10, axis=0)
        hi = np.percentile(P, 90, axis=0)
        m = ((P[:, 0] >= lo[0]) & (P[:, 0] <= hi[0])
             & (P[:, 1] >= lo[1]) & (P[:, 1] <= hi[1]))
        Q = P[m]
        try:
            h = ConvexHull(Q)
            A = h.volume          # 2-D: area
        except Exception:
            A = float("nan")
        rows.append({"year": y, "n": int(m.sum()), "A_km2": A / 1e6,
                     "R": ce_plain(Q, A)})
    R = np.array([r["R"] for r in rows])
    fit = _fit(years, R)
    res["sweeps"]["hull_central80"] = {
        "R_first": float(R[0]), "R_last": float(R[-1]),
        "slope": float(fit["slope"]), "p": float(fit["ols_p"]),
    }

    # fixed-radius disc about the median centre of the full record
    P_all = np.asarray([q for y in years for q in locs_of(yrs[y])], float)
    cx, cy = np.median(P_all, axis=0)
    rows = []
    for r_km in (2.0, 3.0, 5.0):
        r = r_km * 1000.0
        Rr = []
        for y in years:
            P = np.asarray(locs_of(yrs[y]), float)
            d = np.hypot(P[:, 0] - cx, P[:, 1] - cy)
            Q = P[d <= r]
            Rr.append(ce_plain(Q, math.pi * r * r))
        Rr = np.array(Rr)
        fit = _fit(years, Rr)
        res["sweeps"]["disc_%.0fkm" % r_km] = {
            "R_first": float(Rr[0]), "R_last": float(Rr[-1]),
            "slope": float(fit["slope"]), "p": float(fit["ols_p"]),
            "n_last": int((np.hypot(P[:, 0] - cx, P[:, 1] - cy) <= r).sum()),
        }

    json.dump(res, open(here / "results_coredefs.json", "w"), indent=1)

    print("core-definition sensitivity, all on the core window, locations")
    print("  %-18s %8s %8s %9s %8s" % ("core", "R 2013", "R 2026", "slope", "OLS p"))
    for k, v in res["sweeps"].items():
        print("  %-18s %8.3f %8.3f %9.4f %8.3f"
              % (k, v["R_first"], v["R_last"], v["slope"], v["p"]))
    print()
    print("wrote results_coredefs.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

