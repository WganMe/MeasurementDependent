#!/usr/bin/env python3
"""Round-11: per-year urban-extent masks (a level comparison, not a trend check).

For each year build the union of 2 km disks around THAT YEAR's locations, and
compute R on it with its own area. This is an adaptive window (moving-window
confound), so it is reported only as a level comparison. Also print the fixed-mask
rescaling identity constants for the response letter.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np
from scipy.spatial import cKDTree
from scipy.stats import t as tdist

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from analysis_common import ce_r, load_years  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent


def locs_of(d):
    return np.unique(np.round(np.array([(v[0], v[1]) for v in d.values()], float), 1),
                     axis=0)


def mask_area(P, r, ngrid=400):
    lo, hi = P.min(axis=0) - r, P.max(axis=0) + r
    # exact-ish: rasterise at r/20 and count cells within r of any point
    step = r / 20
    xs = np.arange(lo[0], hi[0] + step, step)
    ys = np.arange(lo[1], hi[1] + step, step)
    gx, gy = np.meshgrid(xs, ys)
    S = np.column_stack([gx.ravel(), gy.ravel()])
    inside = cKDTree(P).query(S, k=1)[0] <= r
    return float(inside.sum() * step * step)


def hac(Y, v, lag=2):
    X = np.column_stack([np.ones(len(Y)), Y])
    XtX = np.linalg.pinv(X.T @ X)
    b = XtX @ X.T @ v
    r = v - X @ b
    n, k = X.shape
    S = np.zeros((k, k))
    for t in range(n):
        S += (r[t] ** 2) * (X[t][:, None] @ X[t][:, None].T)
    for l in range(1, lag + 1):
        w = 1 - l / (lag + 1)
        for t in range(l, n):
            G = r[t] * r[t - l] * (X[t][:, None] @ X[t - l][:, None].T)
            S += w * (G + G.T)
    cov = XtX @ S @ XtX
    se = math.sqrt(cov[1, 1])
    return float(b[1]), se


idx = json.loads((HERE / "uo_archive_index.json").read_text())
yrs = load_years(idx)
years = sorted(yrs)
Y = np.array(years, float)
locs = {y: locs_of(yrs[y]) for y in years}
allP = np.vstack(list(locs.values()))
A_fix = mask_area(allP, 2000.0)
A_hull = 4416e6
print("fixed mask (all years) area %.0f km2; sqrt(A_hull/A_fix)=%.3f"
      % (A_fix / 1e6, math.sqrt(A_hull / A_fix)))

rows = []
for y in years:
    P = locs[y]
    A = mask_area(P, 2000.0)
    r = ce_r(P, A)
    rows.append({"year": int(y), "area_km2": A / 1e6, "locations": len(P), "R": r})
    print("  %d  locs %3d  mask %6.0f km2  R %.3f" % (y, len(P), A / 1e6, r))

series = np.array([r["R"] for r in rows])
areas = np.array([r["area_km2"] * 1e6 for r in rows])
b, se = hac(Y, series)
tc = tdist.ppf(0.975, len(Y) - 2)
print("\nper-year mask R: %.3f -> %.3f (%.1f%%); slope %+.4f HAC [%+.4f,%+.4f]"
      % (series[0], series[-1], 100 * (series[-1] - series[0]) / series[0],
         b, b - tc * se, b + tc * se))
print("area range %.0f .. %.0f km2 (ratio %.2f)"
      % (areas.min() / 1e6, areas.max() / 1e6, areas.max() / areas.min()))

(HERE / "results_infill_perm.json").write_text(json.dumps({
    "rows": rows, "series": series.tolist(), "slope": b,
    "ci": [b - tc * se, b + tc * se],
    "fixed_mask_area_km2": A_fix / 1e6,
    "rescale_fixed": math.sqrt(A_hull / A_fix),
}, indent=1))
print("wrote results_infill_perm.json")
