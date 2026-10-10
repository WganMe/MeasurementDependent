#!/usr/bin/env python3
"""Round-8 supplementary: rarefied clustering on the LOCATION unit, and the
fixed-hull sensitivity of the slope to excluding 2017-18 and 2026."""
from __future__ import annotations

import itertools
import json
import math
import pathlib
import sys

import numpy as np
from scipy.spatial import ConvexHull
from scipy.stats import norm, t as tdist

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from analysis_common import ce_r, load_years  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
rng = np.random.default_rng(20261003)


def locs_of(d):
    return np.unique(np.round(np.array([(v[0], v[1]) for v in d.values()], float), 1),
                     axis=0)


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
    tc = tdist.ppf(0.975, n - 2)
    return float(b[1]), se, float(b[1] - tc * se), float(b[1] + tc * se)


def sen(Y, v):
    s = np.sort([(v[j] - v[i]) / (Y[j] - Y[i])
                 for i, j in itertools.combinations(range(len(Y)), 2)])
    n = len(Y); N = len(s)
    varS = n * (n - 1) * (2 * n + 5) / 18.0
    C = norm.ppf(0.975) * math.sqrt(varS)
    k = max(int((N - C) / 2), 0)
    return float(np.median(s)), float(s[k]), float(s[N - k - 1])


idx = json.loads((HERE / "uo_archive_index.json").read_text())
yrs = load_years(idx)
years = sorted(yrs)
Y = np.array(years, float)
all_ids = np.vstack([np.array([(v[0], v[1]) for v in yrs[y].values()], float)
                     for y in years])
A_hull = float(ConvexHull(all_ids).volume)

# rarefied location series at the smallest location count
loc_sets = {y: locs_of(yrs[y]) for y in years}
nmin = min(len(P) for P in loc_sets.values())
print("location counts:", {y: len(loc_sets[y]) for y in years}, "min", nmin)
rare = np.array([float(np.mean([ce_r(P[rng.choice(len(P), nmin, replace=False)], A_hull)
                                for _ in range(1000)])) for P in loc_sets.values()])
full = np.array([ce_r(P, A_hull) for P in loc_sets.values()])
b, se, lo, hi = hac(Y, rare)
s, slo, shi = sen(Y, rare)
print("\nrarefied LOCATION R series:")
for y, v in zip(years, rare):
    print("  %d %.3f" % (y, v))
print("slope %+.5f NW[%+.5f,%+.5f]  Sen %+.5f [%+.5f,%+.5f]" % (b, lo, hi, s, slo, shi))
print("levels %.3f -> %.3f" % (rare[0], rare[-1]))

# fixed-hull sensitivity of the unrarefied location slope
def sub(mask):
    return hac(Y[mask], full[mask])
m_all = np.ones(len(Y), bool)
m_no1718 = ~np.isin(Y, [2017, 2018])
m_no26 = Y != 2026
m_both = m_no1718 & m_no26
print("\nfixed-hull location slope sensitivity (HAC lag2):")
for tag, m in (("all", m_all), ("no 2017-18", m_no1718), ("no 2026", m_no26),
               ("no 2017-18, no 2026", m_both)):
    bb, ss, ll, hh = hac(Y[m], full[m])
    print("  %-20s n=%2d slope %+.5f [%+.5f,%+.5f] se %.5f" % (tag, m.sum(), bb, ll, hh, ss))
print("\nfixed-hull identifier rarefied (N=41) unrarefied loc first/last: %.3f %.3f"
      % (full[0], full[-1]))
(HERE / "results_theilsen_supp.json").write_text(json.dumps({
    "loc_rarefied": rare.tolist(), "loc_full": full.tolist(),
    "loc_rare_nmin": nmin, "loc_rare_slope": b, "loc_rare_ci": [lo, hi],
    "loc_rare_sen": s, "loc_rare_sen_ci": [slo, shi],
}, indent=1))
print("wrote results_theilsen_supp.json")
