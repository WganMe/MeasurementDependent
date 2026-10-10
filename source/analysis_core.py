#!/usr/bin/env python3
"""Round-9 checks: co-location counts, pooled-subset batch test, seed sensitivity.

  R9.1  Co-location share vs surplus, recomputed from the archive index.
  R9.2  Batch-deployment test using a POOLED random-subset null (the random-
        labelling logic), not a homogeneous CSR null.
  R9.3  Seed sensitivity of the rarefied R and Gini series and their slopes.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np
from scipy.spatial import ConvexHull, cKDTree
from scipy.stats import t as tdist

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from analysis_common import ce_r, load_years  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent


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


def ids_pts(d):
    return np.array([(v[0], v[1]) for v in d.values()], float)


def locs_of(d):
    return np.unique(np.round(np.array([(v[0], v[1]) for v in d.values()], float), 1),
                     axis=0)


idx = json.loads((HERE / "uo_archive_index.json").read_text())
yrs = load_years(idx)
years = sorted(yrs)
all_ids = np.vstack([ids_pts(yrs[y]) for y in years])

# ---- R9.1 co-location counts ------------------------------------------------ #
print("[R9.1] co-location, whole record")
n_ids = len(all_ids)
# coordinates at 1e-6 deg rounding (the paper's convention for the share)
round6 = np.round(all_ids, 6)
uniq6 = np.unique(round6, axis=0)
# which identifiers share their coordinate with at least one other
_, inv, counts = np.unique(round6, axis=0, return_inverse=True, return_counts=True)
share = int((counts[inv] > 1).sum())
print("  identifiers %d  distinct coords (1e-6) %d" % (n_ids, len(uniq6)))
print("  SHARE  (share a coordinate) %d = %.1f%%" % (share, 100 * share / n_ids))
print("  SURPLUS (ids - coords)       %d = %.1f%%" % (n_ids - len(uniq6),
                                                      100 * (n_ids - len(uniq6)) / n_ids))
# the paper uses 1899 in-range identifiers and 1567 coordinates
inr = np.vstack([ids_pts(yrs[y]) for y in years])
print("  (paper's in-range population: 1899 identifiers)")

# ---- R9.2 batch test, pooled-subset null ------------------------------------ #
print("\n[R9.2] batch test vs POOLED random subsets (not homogeneous CSR)")
A_hull = float(ConvexHull(all_ids).volume)
rng = np.random.default_rng(20261003)
rows = []
for k in range(1, len(years)):
    prev = locs_of(yrs[years[k - 1]])
    cur = locs_of(yrs[years[k]])
    prevset = {tuple(p) for p in prev}
    new = np.array([p for p in cur if tuple(p) not in prevset])
    if len(new) < 3:
        continue
    pooled = np.vstack([prev, new])
    obs = float(np.median(cKDTree(new).query(new, k=2)[0][:, 1]))
    sims = []
    for _ in range(499):
        sub = pooled[rng.choice(len(pooled), len(new), replace=False)]
        if len(sub) < 3:
            continue
        sims.append(float(np.median(cKDTree(sub).query(sub, k=2)[0][:, 1])))
    sims = np.array(sims)
    lo, hi = np.percentile(sims, [2.5, 97.5])
    # Exact one-sided Monte Carlo p-value: how often a pooled random subset is at
    # least as clustered as the new locations themselves. Stored so the
    # multiplicity correction below has something to correct.
    p_one = float((sims <= obs).mean())
    rows.append({"year": int(years[k]), "n_new": len(new), "obs": obs,
                 "pooled_lo": float(lo), "pooled_hi": float(hi),
                 "p_one_sided": p_one, "n_sims": int(len(sims)),
                 "clustered": bool(obs < lo)})
    print("  %d n=%4d new-new median %6.0f m   pooled-subset [%5.0f,%5.0f]   p=%.3f  %s"
          % (years[k], len(new), obs, lo, hi, p_one,
             "clustered" if obs < lo else ""))
ncl = sum(r["clustered"] for r in rows)
print("  new locations are clustered among themselves in %d of %d year pairs "
      "(pooled-subset null)" % (ncl, len(rows)))

# ---- Benjamini--Hochberg step-up across the year-pair tests ----------------- #
# The tests above are one per consecutive year pair, so they are 13 comparisons,
# not 14, and they share years with one another, so the correction is approximate.
# It is applied anyway because the alternative --- reporting the lowest p-values
# uncorrected --- is what the correction exists to prevent.
def bh_step_up(pvals, alpha=0.05):
    """Return (survivor index set, adjusted p-values, BH threshold)."""
    m = len(pvals)
    order = np.argsort(pvals)
    ranked = np.array(pvals)[order]
    crit = alpha * (np.arange(1, m + 1) / m)
    passing = np.where(ranked <= crit)[0]
    kmax = passing.max() + 1 if len(passing) else 0
    thresh = crit[kmax - 1] if kmax else 0.0
    survive = set(order[:kmax].tolist())
    adj = np.minimum.accumulate((ranked * m / np.arange(1, m + 1))[::-1])[::-1]
    adj = np.clip(adj, 0, 1)
    out = np.empty(m)
    out[order] = adj
    return survive, out.tolist(), float(thresh)

pv = [r["p_one_sided"] for r in rows]
survive, padj, thr = bh_step_up(pv)
for r in rows:
    r["p_adj_bh"] = float(padj[rows.index(r)])
    r["survives_bh"] = bool(rows.index(r) in survive)
surv_years = sorted(r["year"] for r in rows if r["survives_bh"])
print("  [BH] %d of %d year pairs survive at a 5%% false-discovery rate: %s"
      % (len(surv_years), len(rows), surv_years))
print("  [BH] step-up threshold on the ranked p-values: %.4f" % thr)

# ---- R9.3 seed sensitivity -------------------------------------------------- #
print("\n[R9.3] seed sensitivity of the rarefied series")
Y = np.array(years, float)
Ns = np.array([len(ids_pts(yrs[y])) for y in years])
nmin = int(Ns.min())
for seed in (20261003, 20261001, 20261002):
    r = np.random.default_rng(seed)
    rare = np.array([float(np.mean([ce_r(ids_pts(yrs[y])[r.choice(Ns[i], nmin,
                    replace=False)], A_hull) for _ in range(1000)]))
                    for i, y in enumerate(years)])
    b, se, lo, hi = hac(Y, rare)
    print("  seed %d: rarefied R slope %+.5f  HAC [%+.5f,%+.5f]  se %.5f  "
          "2013 %.3f  2026 %.3f" % (seed, b, lo, hi, se, rare[0], rare[-1]))

(HERE / "results_core.json").write_text(json.dumps({
    "share": share, "share_pct": 100 * share / n_ids, "n_ids": n_ids,
    "surplus": int(n_ids - len(uniq6)), "n_coords": int(len(uniq6)),
    "batch_pooled": rows, "batch_clustered": ncl,
    "bh_pooled_survivors": surv_years, "bh_pooled_threshold": thr,
    "bh_pooled_n_tests": len(rows),
}, indent=1))
print("\nwrote results_core.json")
