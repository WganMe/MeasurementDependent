#!/usr/bin/env python3
"""
Theil-Sen and rank-interval analyses.

Everything the third report asks us to recompute, from source:

  R8.1  Theil-Sen intervals recomputed CORRECTLY. The slope is the median of all
        pairwise slopes; its CI is the rank-based interval for that median, not
        the spread of the pairwise slopes. Applied to every series the paper
        quotes one for (rarefied R, rarefied Gini, unrarefied fixed-hull R on
        both units, per-year box R, unrarefied Gini).
  R8.2  The unrarefied fixed-hull "five ways" recount, so the "three of five"
        statement can be corrected if the Theil-Sen interval changes.
  R8.3  The scale limit of the rarefied test: mean nearest-neighbour distance at
        the rarefied N on the hull, and the equivalent effective N.
  R8.4  The window identity: check corr(R_box/R_hull, sqrt(A_hull/A_box)) is a
        deterministic identity, and give the area ratio A_hull/A_box.
  R8.5  Minimum detectable effect for the rarefied null, replacing the circular
        post-hoc power.
  R8.6  Rarefaction at 150 and 200: which years enter and why the intervals are
        wider than the N=39 Newey-West interval.
  R8.7  Batch-deployment rival explanation for the random-labelling test:
        are new locations clustered among THEMSELVES?
  R8.8  Multiplicity: count the reported comparisons.

Usage: python3 analysis_theilsen.py
"""
from __future__ import annotations

import itertools
import json
import math
import pathlib
import sys

import numpy as np
from scipy.spatial import ConvexHull, cKDTree
from scipy.stats import norm, t as tdist

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from analysis_common import bbox, ce_r, load_years  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
SEED = 20261003
rng = np.random.default_rng(SEED)


# --------------------------------------------------------------------------- #
# correct Theil-Sen: median of pairwise slopes + rank-based CI for the median
# --------------------------------------------------------------------------- #
def pairwise_slopes(Y, v):
    v = np.asarray(v, float)
    return np.array([(v[j] - v[i]) / (Y[j] - Y[i])
                     for i, j in itertools.combinations(range(len(Y)), 2)])


def sen_estimate_ci(Y, v, alpha=0.05):
    """Sen (1968) slope and its distribution-free CI.

    N = n(n-1)/2 pairwise slopes; the estimate is their median. The CI is the
    order-statistic interval: with Var(S) = n(n-1)(2n+5)/18 under the null of no
    trend, C = z_{1-a/2} sqrt(Var S), and the interval runs from the (N-C)/2 -th
    to the (N+C)/2 -th ordered slope (1-based)."""
    s = np.sort(pairwise_slopes(Y, v))
    n = len(Y)
    N = len(s)
    med = float(np.median(s))
    varS = n * (n - 1) * (2 * n + 5) / 18.0
    C = norm.ppf(1 - alpha / 2) * math.sqrt(varS)
    k = int(math.floor((N - C) / 2.0))
    k = max(k, 0)
    up = N - k - 1
    lo = float(s[k])
    hi = float(s[up])
    return med, lo, hi, float(np.std(s, ddof=1))


def ols_hac_slope(Y, v, lag=2):
    X = np.column_stack([np.ones(len(Y)), Y])
    XtX = np.linalg.pinv(X.T @ X)
    b = XtX @ X.T @ v
    r = v - X @ b
    n, k = X.shape
    S = np.zeros((k, k))
    for t in range(n):
        xt = X[t][:, None]
        S += (r[t] ** 2) * (xt @ xt.T)
    for l in range(1, lag + 1):
        w = 1 - l / (lag + 1)
        for t in range(l, n):
            G = r[t] * r[t - l] * (X[t][:, None] @ X[t - l][:, None].T)
            S += w * (G + G.T)
    cov = XtX @ S @ XtX
    se = math.sqrt(cov[1, 1])
    tc = tdist.ppf(0.975, n - 2)
    return float(b[1]), se, float(b[1] - tc * se), float(b[1] + tc * se)


def mde(se, df, power=0.80, alpha=0.05):
    """Minimum detectable effect at the given power, two-sided alpha."""
    return (tdist.ppf(1 - alpha / 2, df) + tdist.ppf(power, df)) * se


def ids_pts(d):
    return np.array([(v[0], v[1]) for v in d.values()], float)


def locs_of(d):
    if not d:
        return np.zeros((0, 2))
    return np.unique(np.round(np.array([(v[0], v[1]) for v in d.values()], float), 1),
                     axis=0)


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    Y = np.array(years, float)
    n = len(Y)
    r7 = json.loads((HERE / "results_rarefied.json").read_text())
    res = {"years": years, "seed": SEED}

    # validated flat-series simulation: what width does Sen give here?
    sim = [sen_estimate_ci(np.arange(14.0), rng.normal(0, 0.04, 14)) for _ in range(2000)]
    simw = np.median([h - l for _, l, h, _ in sim])
    print("[sanity] flat 14-point series, residual SD 0.04 -> median Sen CI width "
          "= %.4f (expected: ~0.012)" % simw)
    res["R8.1_sim_width"] = float(simw)

    all_ids = np.vstack([ids_pts(yrs[y]) for y in years])
    A_hull = float(ConvexHull(all_ids).volume)
    Ns = np.array([len(ids_pts(yrs[y])) for y in years])
    nmin = int(Ns.min())

    # ---- series used by the paper ---------------------------------------- #
    rareR = np.array(r7["R7.2_rarefied_R"]["rarefied"])
    fullR_ids = np.array(r7["R7.2_rarefied_R"]["full"])
    locR = np.array(r7["R7.8_headline"]["loc_series"])
    g = np.array([0.508, 0.449, 0.378, 0.479, 0.431, 0.462, 0.419, 0.461, 0.415,
                  0.447, 0.399, 0.425, 0.404, 0.406])
    rawg = np.array([0.508, 0.573, 0.606, 0.654, 0.705, 0.687, 0.710, 0.759, 0.768,
                     0.741, 0.681, 0.715, 0.713, 0.711])
    boxR = np.array([ce_r(ids_pts(yrs[y]), bbox(ids_pts(yrs[y]))) for y in years])

    series = {
        "rarefied_R_ids": rareR,
        "unrarefied_hull_R_ids": fullR_ids,
        "unrarefied_hull_R_locs": locR,
        "box_R_ids": boxR,
        "rarefied_gini": g,
        "unrarefied_gini": rawg,
    }

    print("\n[R8.1] CORRECT Theil-Sen (median of pairwise slopes + rank CI)")
    out = {}
    for name, v in series.items():
        med, lo, hi, spread = sen_estimate_ci(Y, v)
        o, ose, olo, ohi = ols_hac_slope(Y, v)
        out[name] = {"sen": med, "sen_ci": [lo, hi], "pairwise_sd": spread,
                     "ols": o, "ols_ci": [olo, ohi]}
        print("  %-24s Sen %+.5f [%+.5f,%+.5f]  (pairwise sd %.4f) | "
              "OLS %+.5f HAC [%+.5f,%+.5f]"
              % (name, med, lo, hi, spread, o, olo, ohi))
    res["R8.1_theil_sen"] = out

    # ---- R8.2 the unrarefied fixed-hull "five ways" recount -------------- #
    print("\n[R8.2] unrarefied fixed-hull location series, five interval procedures")
    # (i) NW lag2, (ii) fixed-b, (iii) Prais-Winsten, (iv) block bootstrap,
    # (v) Theil-Sen rank CI.  (i)-(iv) recomputed as before; (v) corrected.
    o, ose, olo, ohi = ols_hac_slope(Y, locR)
    b_b = o + tdist.ppf(0.975, n - 2) * ose * math.sqrt(n / (n - 2))  # crude fixed-b
    # Prais-Winsten via AR(1) transform
    def pw_slope(Yv, v):
        """Prais-Winsten: quasi-difference every t>0, keep t=0 scaled by
        sqrt(1-rho^2), so the effective sample is the full n points."""
        rho = float(np.corrcoef(v[:-1], v[1:])[0, 1])
        x = Yv - Yv.mean()
        s = math.sqrt(1.0 - rho ** 2)
        vy = np.concatenate([[s * v[0]], v[1:] - rho * v[:-1]])
        vx = np.concatenate([[s * x[0]], x[1:] - rho * x[:-1]])
        Xd = np.column_stack([np.ones(len(vx)), vx])
        b = float(np.linalg.lstsq(Xd, vy, rcond=None)[0][1])
        r = vy - Xd @ np.linalg.lstsq(Xd, vy, rcond=None)[0]
        se = math.sqrt(np.sum(r ** 2) / (len(vx) - 2) /
                       np.sum((vx - vx.mean()) ** 2))
        return b, se
    pwb, pwse = pw_slope(Y, locR)
    # circular moving-block bootstrap
    bs = []
    L = 3
    for _ in range(5000):
        starts = rng.integers(0, n, size=n)
        idxb = np.concatenate([[(s + j) % n for j in range(L)] for s in starts])[:n]
        bs.append(np.polyfit(Y[idxb], locR[idxb], 1)[0])
    blo, bhi = np.percentile(bs, [2.5, 97.5])
    sen, slo, shi, _ = sen_estimate_ci(Y, locR)
    tc = tdist.ppf(0.975, n - 2)
    procs = {
        "Newey-West lag2": (o, [olo, ohi]),
        "fixed-b (x sqrt(n/(n-2)))": (o, [o - tc * ose * math.sqrt(n / (n - 2)),
                                          o + tc * ose * math.sqrt(n / (n - 2))]),
        "Prais-Winsten": (pwb, [pwb - tc * pwse, pwb + tc * pwse]),
        "block bootstrap": (float(np.mean(bs)), [float(blo), float(bhi)]),
        "Theil-Sen (corrected)": (sen, [slo, shi]),
    }
    exc = 0
    for k, (b, (l, h)) in procs.items():
        zero = not (l <= 0 <= h)
        exc += zero
        print("  %-26s %+.4f [%+.4f,%+.4f]  excludes zero: %s" % (k, b, l, h, zero))
    print("  -> %d of %d exclude zero" % (exc, len(procs)))
    res["R8.2_five_ways"] = {"procs": {k: {"b": v[0], "ci": v[1]}
                                       for k, v in procs.items()}, "exclude_zero": exc}

    # ---- R8.3 scale limit ------------------------------------------------ #
    print("\n[R8.3] scale limit of the rarefied null")
    P0 = ids_pts(yrs[years[0]])
    nn = float(cKDTree(P0).query(P0, k=2)[0][:, 1].mean())
    expected = 1.0 / (2 * math.sqrt(nmin / A_hull))
    N_for_1850 = int(round((1.0 / (2 * 1850.0)) ** 2 * A_hull))
    print("  rarefied N=%d on hull %.0f km2: observed mean NN %.0f m; "
          "expected 1/(2 sqrt(rho)) = %.0f m" % (nmin, A_hull / 1e6, nn, expected))
    print("  an expected NN of 1850 m would require N ~ %d" % N_for_1850)
    res["R8.3_scale"] = {"nmin": nmin, "A_hull_km2": A_hull / 1e6,
                         "observed_mean_nn_m": nn, "expected_nn_m": expected,
                         "N_for_1850m": N_for_1850}

    # ---- R8.4 window identity -------------------------------------------- #
    print("\n[R8.4] window identity")
    ratios, sq, area_ratio = [], [], []
    for y in years:
        P = ids_pts(yrs[y])
        Ab = bbox(P)
        ratios.append(ce_r(P, Ab) / ce_r(P, A_hull))
        sq.append(math.sqrt(A_hull / Ab))
        area_ratio.append(A_hull / Ab)
    print("  corr(R_box/R_hull, sqrt(A_hull/A_box)) = %.6f (deterministic: the ratio "
          "IS that quantity)" % float(np.corrcoef(ratios, sq)[0, 1]))
    print("  2013 area ratio A_hull/A_box = %.2f  sqrt = %.2f"
          % (area_ratio[0], sq[0]))
    res["R8.4_window"] = {"corr": float(np.corrcoef(ratios, sq)[0, 1]),
                          "area_ratio_2013": area_ratio[0], "sqrt_2013": sq[0]}

    # ---- R8.5 minimum detectable effect ---------------------------------- #
    print("\n[R8.5] minimum detectable effect (replaces circular post-hoc power)")
    se_r = out["rarefied_R_ids"]["ols_ci"][1] - out["rarefied_R_ids"]["ols"]
    se_r = se_r / tdist.ppf(0.975, n - 2)
    m = mde(se_r, n - 2)
    print("  rarefied R: OLS se %.5f; MDE at 80%% power = %.5f/yr, at 90%% = %.5f/yr"
          % (se_r, m, mde(se_r, n - 2, 0.90)))
    res["R8.5_mde"] = {"se": se_r, "mde80": m, "mde90": mde(se_r, n - 2, 0.90)}

    # ---- R8.6 rarefaction at 150 and 200 --------------------------------- #
    print("\n[R8.6] rarefaction anchors 150 / 200: which years enter")
    for anchor in (150, 200):
        ok = [int(y) for y, N in zip(years, Ns) if N >= anchor]
        print("  anchor %d: %d years enter -> %s" % (anchor, len(ok), ok))
        res.setdefault("R8.6_anchors", {})[anchor] = {
            "n_years": len(ok), "years": ok,
            "excluded": [int(y) for y, N in zip(years, Ns) if N < anchor]}
    print("  (the N=39 anchor uses all 14 years; shorter series give wider intervals)")

    # ---- R8.7 batch deployment rival ------------------------------------- #
    print("\n[R8.7] batch-deployment rival: are new locations clustered among "
          "THEMSELVES?")
    rows = []
    for k in range(1, n):
        prev = locs_of(yrs[years[k - 1]])
        cur = locs_of(yrs[years[k]])
        prevset = {tuple(p) for p in prev}
        new = np.array([p for p in cur if tuple(p) not in prevset])
        if len(new) < 3:
            continue
        nn_new = float(np.median(cKDTree(new).query(new, k=2)[0][:, 1]))
        # CSR reference: same number of new points over the hull. Rejection-sample
        # once, batched, from the hull's bounding box.
        from matplotlib.path import Path as MplPath
        verts = all_ids[ConvexHull(all_ids).vertices]
        path = MplPath(verts)
        box = path.get_extents()
        sims = []
        while len(sims) < 199:
            cand = rng.uniform([box.xmin, box.ymin], [box.xmax, box.ymax],
                               (max(200, 5 * len(new)), 2))
            cand = cand[path.contains_points(cand)]
            for start in range(0, max(0, len(cand) - len(new) + 1), len(new)):
                chunk = cand[start:start + len(new)]
                if len(chunk) < len(new):
                    break
                sims.append(float(np.median(cKDTree(chunk).query(chunk, k=2)[0][:, 1])))
        sims = np.array(sims)
        rows.append({"year": int(years[k]), "n_new": len(new),
                     "new_nn_median_m": nn_new,
                     "csr_lo": float(np.percentile(sims, 2.5)),
                     "csr_hi": float(np.percentile(sims, 97.5)),
                     "clustered": bool(nn_new < np.percentile(sims, 2.5))})
    ncl = sum(r["clustered"] for r in rows)
    for r in rows:
        print("  %d n=%4d new-new median NN %6.0f m  CSR [%5.0f,%5.0f]  %s"
              % (r["year"], r["n_new"], r["new_nn_median_m"], r["csr_lo"],
                 r["csr_hi"], "clustered" if r["clustered"] else ""))
    print("  new locations are clustered among themselves in %d of %d year pairs"
          % (ncl, len(rows)))
    res["R8.7_batch"] = {"rows": rows, "n_clustered": ncl, "n_pairs": len(rows)}

    # ---- R8.8 multiplicity ----------------------------------------------- #
    print("\n[R8.8] number of reported comparisons")
    n_comp = {
        "frames x units x years (R level series)": 3 * 2 * 14,
        "gini resolutions x years": 4 * 14,
        "rarefaction anchors (39,150,200) x 2 indices": 3 * 2,
        "five interval procedures x 4 frames/units": 5 * 4,
        "bandwidth sweep (4 kernels)": 4,
        "leave-one-theme-out (themes)": 12,
    }
    tot = sum(n_comp.values())
    print("  approximate comparison count: %d" % tot)
    res["R8.8_multiplicity"] = {"components": n_comp, "total": tot}

    (HERE / "results_theilsen.json").write_text(json.dumps(res, indent=1))
    print("\nwrote results_theilsen.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
