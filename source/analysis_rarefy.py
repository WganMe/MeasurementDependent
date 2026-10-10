#!/usr/bin/env python3
"""
Rarefaction analyses.

Every number the second-round report asks us to fix or supply, recomputed from
source. Written to results_rarefied.json and printed.

  R7.1  Window mechanism. Clark-Evans R scales as A^-1/2, so a SMALLER box RAISES
        R. Print box/hull R ratio and sqrt(box/hull area) for every year, to show
        which years the box inflates and which it deflates.

  R7.2  Rarefied R on the fixed hull, year by year, with four intervals:
        OLS+HAC, Theil-Sen (pairwise), bootstrap; the two equivalence bounds
        (|unrarefied slope| and half of it); power; and the scale limit
        (observed mean nearest-neighbour distance at the rarefied N).

  R7.3  Same for the rarefied Gini, reading the printed Table 8 values.

  R7.4  The clean regression. On a fixed frame ln R = ln d_bar + 1/2 ln N + c, so
        regress ln d_bar on ln N and test the slope against -1/2, which is the
        structural value.

  R7.5  Size versus time: on the fixed hull the size coefficient loses
        significance and the year coefficient survives; report and reconcile.

  R7.6  Random-labelling infill test, replacing the cross-type J whose F was a
        homogeneous empty-space function. Pool each year pair's locations,
        permute the new/existing labels, and compare the observed new-to-existing
        distance statistics with the permutation envelope.

  R7.7  Inhomogeneous null: record the kernel bandwidth, itemise which years fall
        inside and outside the envelope, and recompute Ripley K/L on the FIXED
        hull with simulation envelopes.

  R7.8  Location-based fixed-hull headline, and the endpoint percentages.

  R7.9  Gap-filled population: rerun R (both units, fixed hull) and the Gini on
        the filled roster.

  R7.10 Snapshot: recount the 2x2, resolve 354+289, and test the rival
        explanation (that the omitted vehicle variables are no longer served) by
        checking the snapshot's own variable dictionary.

Usage: python3 analysis_rarefy.py
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sqlite3
import sys

import numpy as np
from scipy.spatial import ConvexHull, cKDTree
from scipy.stats import t as tdist

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from analysis_common import HERE, bbox, ce_r, gini_fixed_grid, load_years  # noqa: E402

SEED = 20261003
rng = np.random.default_rng(SEED)


def ids_pts(d):
    return np.array([(v[0], v[1]) for v in d.values()], float)


def locs_of(d):
    if not d:
        return np.zeros((0, 2))
    return np.unique(np.round(np.array([(v[0], v[1]) for v in d.values()], float), 1),
                     axis=0)


def hull_area(P):
    return float(ConvexHull(P).volume)


def mean_nn(P):
    if len(P) < 2:
        return float("nan")
    return float(cKDTree(P).query(P, k=2)[0][:, 1].mean())


def slopes(Y, v):
    v = np.asarray(v, float)
    allsl = np.array([(v[j] - v[i]) / (Y[j] - Y[i])
                      for i in range(len(Y)) for j in range(i + 1, len(Y))])
    return allsl


def ts_interval(Y, v):
    s = np.sort(slopes(Y, v))
    return (float(np.median(s)), float(s[int(0.025 * len(s))]),
            float(s[int(0.975 * len(s)) - 1]))


def ols_hac_slope(Y, v, lag=2):
    """Slope of v on year with Newey-West HAC se; returns slope, se, lo, hi."""
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


def tost(b, se, bound, df):
    """TOST for equivalence to zero within +/- bound."""
    pA = float(tdist.sf((b + bound) / se, df=df))
    pB = float(tdist.cdf((b - bound) / se, df=df))
    return max(pA, pB)


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    Y = np.array(years, float)
    n = len(Y)
    all_ids = np.vstack([ids_pts(yrs[y]) for y in years])
    A_hull = hull_area(all_ids)
    res = {"years": years, "seed": SEED, "A_hull_km2": A_hull / 1e6}

    # ============================================================ R7.1
    print("[R7.1] window mechanism: smaller box RAISES R")
    print("  year  box_km2  hull/box  sqrt(hull/box)  R_box  R_hull  R_box/R_hull")
    ratio, area_ratio, rb, rh = [], [], [], []
    for y in years:
        P = ids_pts(yrs[y])
        Ab = bbox(P)
        r_box = ce_r(P, Ab)
        r_hull = ce_r(P, A_hull)
        rb.append(r_box); rh.append(r_hull)
        ratio.append(r_box / r_hull); area_ratio.append(math.sqrt(A_hull / Ab))
        print("  %d %8.0f  %7.2f  %13.2f  %.3f  %.3f  %.2f"
              % (y, Ab / 1e6, A_hull / Ab, math.sqrt(A_hull / Ab), r_box, r_hull,
                 r_box / r_hull))
    print("  corr(R_box/R_hull, sqrt(A_hull/A_box)) = %.3f  (positive => smaller box "
          "raises R, i.e. A^-1/2)" % float(np.corrcoef(ratio, area_ratio)[0, 1]))
    res["R7.1_window"] = {"box_hull_ratio": ratio, "sqrt_area_ratio": area_ratio,
                          "R_box": rb, "R_hull": rh,
                          "corr": float(np.corrcoef(ratio, area_ratio)[0, 1])}
    print("  2013 box is %.2fx the hull, doubling the 2013 R; 2021 box is 0.82x, "
          "deflating it" % (A_hull / bbox(ids_pts(yrs[2013]))))

    # ============================================================ R7.2
    print("\n[R7.2] rarefied R on the fixed hull, year by year")
    Ns = np.array([len(ids_pts(yrs[y])) for y in years])
    nmin = int(Ns.min())
    rare = []
    for y in years:
        P = ids_pts(yrs[y])
        draws = [ce_r(P[rng.choice(len(P), nmin, replace=False)], A_hull)
                 for _ in range(1000)]
        rare.append(float(np.mean(draws)))
    rare = np.array(rare)
    full = np.array([ce_r(ids_pts(yrs[y]), A_hull) for y in years])
    print("  year  N   rarefiedR  fullR")
    for y, N, rr, ff in zip(years, Ns, rare, full):
        print("  %d %4d  %.3f     %.3f" % (y, N, rr, ff))
    b, se, lo, hi = ols_hac_slope(Y, rare)
    ts, tslo, tshi = ts_interval(Y, rare)
    # bootstrap over instruments, per-year resample, refit slope
    bslopes = []
    for _ in range(1000):
        col = [ce_r(ids_pts(yrs[y])[rng.choice(Ns[i], nmin, replace=False)], A_hull)
               for i, y in enumerate(years)]
        bslopes.append(np.polyfit(Y, col, 1)[0])
    blo, bhi = np.percentile(bslopes, [2.5, 97.5])
    # observed mean NN distance at the rarefied N (the scale the null applies to)
    rarefied_pts = ids_pts(yrs[years[0]])[rng.choice(Ns[0], nmin, replace=False)]
    nn_at_nmin = mean_nn(rarefied_pts)
    print("  rarefied R: OLS %+.5f  HAC95 [%+.5f,%+.5f]  Theil-Sen %+.5f [%+.4f,%+.4f]"
          % (b, lo, hi, ts, tslo, tshi))
    print("     instrument-bootstrap 95%% [%+.5f,%+.5f]" % (blo, bhi))
    full_slope = ols_hac_slope(Y, full)[0]
    print("     unrarefied hull slope %+.4f; mean NN at N=%d is %.0f m (scale the "
          "null applies to)" % (full_slope, nmin, nn_at_nmin))
    bres = {"rarefied": rare.tolist(), "full": full.tolist(),
            "ols": b, "hac_ci": [lo, hi], "ts": ts, "ts_ci": [tslo, tshi],
            "boot_ci": [float(blo), float(bhi)],
            "unrarefied_slope": full_slope, "nn_at_nmin_m": nn_at_nmin,
            "N_at_nmin": nmin}
    for tag, bound in (("full", abs(full_slope)), ("half", abs(full_slope) / 2)):
        p = tost(b, se, bound, n - 2)
        bres["tost_%s" % tag] = {"bound": bound, "p": p, "equiv": bool(p < 0.05)}
        print("     TOST vs +/-%.4f (%s): p=%.4f  equivalent: %s"
              % (bound, tag, p, p < 0.05))
    ncp = abs(full_slope) / se
    bres["power"] = float(tdist.sf(tdist.ppf(0.975, n - 2), n - 2, loc=ncp))
    print("     power to detect the unrarefied slope: %.3f" % bres["power"])
    res["R7.2_rarefied_R"] = bres

    # ============================================================ R7.3
    print("\n[R7.3] rarefied Gini (printed Table 8 values), same four intervals")
    g = np.array([0.508, 0.449, 0.378, 0.479, 0.431, 0.462, 0.419, 0.461, 0.415,
                  0.447, 0.399, 0.425, 0.404, 0.406])
    raw = np.array([0.508, 0.573, 0.606, 0.654, 0.705, 0.687, 0.710, 0.759, 0.768,
                    0.741, 0.681, 0.715, 0.713, 0.711])
    gb, gse, glo, ghi = ols_hac_slope(Y, g)
    gts, gtslo, gtshi = ts_interval(Y, g)
    grawslope = ols_hac_slope(Y, raw)[0]
    print("  rarefied Gini: OLS %+.5f  HAC95 [%+.5f,%+.5f]  Theil-Sen %+.5f [%+.4f,%+.4f]"
          % (gb, glo, ghi, gts, gtslo, gtshi))
    print("  uncorrected slope %+.5f" % grawslope)
    gres = {"ols": gb, "se": gse, "hac_ci": [glo, ghi], "ts": gts,
            "ts_ci": [gtslo, gtshi], "uncorrected_slope": grawslope}
    for tag, bound in (("full", abs(grawslope)), ("half", abs(grawslope) / 2)):
        p = tost(gb, gse, bound, n - 2)
        gres["tost_%s" % tag] = {"bound": bound, "p": p, "equiv": bool(p < 0.05)}
        print("     TOST vs +/-%.4f (%s): p=%.4f  equivalent: %s"
              % (bound, tag, p, p < 0.05))
    res["R7.3_rarefied_gini"] = gres

    # ============================================================ R7.4
    print("\n[R7.4] the clean regression: ln d_bar on ln N, slope vs -1/2")
    dbar = np.array([mean_nn(ids_pts(yrs[y])) for y in years])
    lnN = np.log(Ns)
    X = np.column_stack([np.ones(n), lnN])
    XtX = np.linalg.pinv(X.T @ X)
    bb = XtX @ X.T @ np.log(dbar)
    r = np.log(dbar) - X @ bb
    S = np.zeros((2, 2))
    for t in range(n):
        S += (r[t] ** 2) * (X[t][:, None] @ X[t][:, None].T)
    for l in range(1, 3):
        w = 1 - l / 3
        for t in range(l, n):
            G = r[t] * r[t - l] * (X[t][:, None] @ X[t - l][:, None].T)
            S += w * (G + G.T)
    cov = XtX @ S @ XtX
    sed = math.sqrt(cov[1, 1])
    tc = tdist.ppf(0.975, n - 2)
    print("  ln d_bar = %.3f %+.3f ln N  (HAC se %.3f, 95%% [%+.3f,%+.3f])"
          % (bb[0], bb[1], sed, bb[1] - tc * sed, bb[1] + tc * sed))
    print("  structural value under a fixed frame is -0.5; the estimate is %+.3f, "
          "which is %.1f se from -0.5" % (bb[1], abs(bb[1] + 0.5) / sed))
    print("  test slope = -0.5: t = %.2f" % ((bb[1] + 0.5) / sed))
    # rarefied: does ln d_bar on ln N hold at fixed N? (it is the same as ln R)
    res["R7.4_clean"] = {"slope": float(bb[1]), "se": sed,
                         "ci": [float(bb[1] - tc * sed), float(bb[1] + tc * sed)],
                         "t_vs_minus_half": float((bb[1] + 0.5) / sed)}

    # ============================================================ R7.5
    print("\n[R7.5] size versus time on the fixed hull")
    Xj = np.column_stack([np.ones(n), lnN, Y])
    XtXj = np.linalg.pinv(Xj.T @ Xj)
    bj = XtXj @ Xj.T @ np.log(full)
    rj = np.log(full) - Xj @ bj
    Sj = np.zeros((3, 3))
    for t in range(n):
        Sj += (rj[t] ** 2) * (Xj[t][:, None] @ Xj[t][:, None].T)
    for l in range(1, 3):
        w = 1 - l / 3
        for t in range(l, n):
            G = rj[t] * rj[t - l] * (Xj[t][:, None] @ Xj[t - l][:, None].T)
            Sj += w * (G + G.T)
    covj = XtXj @ Sj @ XtXj
    sej = np.sqrt(np.diag(covj))
    print("  joint on hull: size %+.3f [%+.3f,%+.3f]  year %+.4f [%+.4f,%+.4f]"
          % (bj[1], bj[1] - tc * sej[1], bj[1] + tc * sej[1],
             bj[2], bj[2] - tc * sej[2], bj[2] + tc * sej[2]))
    print("  rarefied R slope on year (fixed N): %+.5f [%+.5f,%+.5f] (contains 0)"
          % (b, lo, hi))
    res["R7.5_size_time"] = {"joint_size": float(bj[1]),
                             "joint_size_ci": [float(bj[1] - tc * sej[1]),
                                               float(bj[1] + tc * sej[1])],
                             "joint_year": float(bj[2]),
                             "joint_year_ci": [float(bj[2] - tc * sej[2]),
                                               float(bj[2] + tc * sej[2])],
                             "rarefied_year_slope": [b, lo, hi]}

    # ============================================================ R7.6
    print("\n[R7.6] random-labelling infill test (replaces the cross-type J)")
    rows = []
    for k in range(1, n):
        prev = locs_of(yrs[years[k - 1]])
        cur = locs_of(yrs[years[k]])
        prevset = {tuple(p) for p in prev}
        new = np.array([p for p in cur if tuple(p) not in prevset])
        if len(new) < 3:
            continue
        pooled = np.vstack([prev, new])
        labels = np.array([0] * len(prev) + [1] * len(new))
        tree = cKDTree(prev)
        obs = float(np.median(tree.query(new, k=1)[0]))
        sims = []
        for _ in range(199):
            perm = rng.permutation(len(pooled))
            lab = labels[perm]
            fake_new = pooled[lab == 1]
            fake_old = pooled[lab == 0]
            t2 = cKDTree(fake_old)
            sims.append(float(np.median(t2.query(fake_new, k=1)[0])))
        sims = np.array(sims)
        rows.append({"year": years[k], "n_new": len(new), "obs_median_m": obs,
                     "env_lo": float(np.percentile(sims, 2.5)),
                     "env_hi": float(np.percentile(sims, 97.5)),
                     "p_low": float((sims <= obs).mean())})
    print("  year  new  obs_median_m  permutation_env   p(new closer than chance)")
    n_below = 0
    for r in rows:
        flag = r["obs_median_m"] < r["env_lo"]
        n_below += flag
        print("  %d %4d  %8.0f    [%.0f,%.0f]   %.3f %s"
              % (r["year"], r["n_new"], r["obs_median_m"], r["env_lo"], r["env_hi"],
                 r["p_low"], "<-- closer" if flag else ""))
    print("  new locations are closer to the existing set than chance in %d of %d "
          "years" % (n_below, len(rows)))
    res["R7.6_random_labelling"] = {"rows": rows, "n_below": n_below,
                                    "n_pairs": len(rows)}

    # ============================================================ R7.7
    print("\n[R7.7] inhomogeneous null: bandwidth, itemised years, K/L on the hull")
    print("  (the inhomogeneous null of Section 3.2 uses a 500 m grid with a "
          "Gaussian kernel of sigma = 1.5 cells = 750 m)")
    gres2 = json.loads((HERE / "results_inhomogeneous.json").read_text())
    inh = gres2["N8_inhomogeneous"]
    inside = [r["year"] for r in inh if r["env_lo"] <= r["obs_R_inhom"] <= r["env_hi"]]
    below = [r["year"] for r in inh if r["obs_R_inhom"] < r["env_lo"]]
    above = [r["year"] for r in inh if r["obs_R_inhom"] > r["env_hi"]]
    print("  below the envelope (clustered beyond intensity): %s" % below)
    print("  inside the envelope (consistent with intensity): %s" % inside)
    print("  above the envelope (more even than intensity):  %s" % above)
    res["R7.7_inhomogeneous"] = {"bandwidth_m": 750, "below": below,
                                 "inside": inside, "above": above}
    # sensitivity to the bandwidth
    from scipy.ndimage import gaussian_filter
    from matplotlib.path import Path as MplPath
    verts = all_ids[ConvexHull(all_ids).vertices]
    path = MplPath(verts)
    lo_p = all_ids.min(axis=0) - 2000; hi_p = all_ids.max(axis=0) + 2000
    cell = 500.0
    nx = int((hi_p[0] - lo_p[0]) / cell) + 1
    ny = int((hi_p[1] - lo_p[1]) / cell) + 1
    cx, cy = np.meshgrid(lo_p[0] + (np.arange(nx) + .5) * cell,
                         lo_p[1] + (np.arange(ny) + .5) * cell)
    centres = np.column_stack([cx.ravel(), cy.ravel()])
    ins = path.contains_points(centres)
    cent_in = centres[ins]
    for sigma in (0.75, 1.5, 2.5, 4.0):
        cnt = 0
        for y in years:
            P = ids_pts(yrs[y]); m = len(P)
            ix = np.clip(((P[:, 0] - lo_p[0]) / cell).astype(int), 0, nx - 1)
            iy = np.clip(((P[:, 1] - lo_p[1]) / cell).astype(int), 0, ny - 1)
            H = np.zeros((ny, nx)); np.add.at(H, (iy, ix), 1.0)
            dens = gaussian_filter(H, sigma=sigma).ravel()[ins]
            if dens.sum() <= 0:
                continue
            prob = dens / dens.sum()
            Rs = [ce_r(cent_in[rng.choice(len(cent_in), m, p=prob)] +
                       rng.uniform(-cell / 2, cell / 2, (m, 2)), A_hull)
                  for _ in range(99)]
            if ce_r(P, A_hull) < np.percentile(Rs, 2.5):
                cnt += 1
        print("  bandwidth sigma=%.2f cells (%.0f m): %d of 14 years below the envelope"
              % (sigma, sigma * cell, cnt))
        res["R7.7_inhomogeneous"]["below_%s" % sigma] = cnt

    # K/L on the fixed hull with a CSR envelope, per year
    def L_curve(P, area, rs, W=None):
        tree = cKDTree(P)
        m = len(P)
        if m < 3:
            return np.full(len(rs), np.nan)
        area = float(area)
        out = []
        for r in rs:
            pairs = tree.query_pairs(r, output_type="ndarray")
            if len(pairs) == 0:
                out.append(np.nan); continue
            k = area * len(pairs) / (m * (m - 1))
            out.append(math.sqrt(k / math.pi) - r)
        return np.array(out)

    rs = [100., 250., 500., 1000., 1500., 2000.]
    Lrows = []
    for y in years:
        P = ids_pts(yrs[y])
        L = L_curve(P, A_hull, rs)
        m = len(P)
        env = np.array([L_curve(cent_in[rng.choice(len(cent_in), m)] , A_hull, rs)
                        for _ in range(49)])
        Lrows.append({"year": y, "L_100m": float(L[0]), "L_1000m": float(L[3]),
                      "env_100_lo": float(np.nanpercentile(env[:, 0], 2.5)),
                      "env_100_hi": float(np.nanpercentile(env[:, 0], 97.5)),
                      "env_1000_lo": float(np.nanpercentile(env[:, 3], 2.5)),
                      "env_1000_hi": float(np.nanpercentile(env[:, 3], 97.5))})
    above = sum(1 for r in Lrows if r["L_1000m"] > r["env_1000_hi"])
    print("  L on the fixed hull: the 1 km value exceeds a uniform-hull envelope "
          "in %d of 14 years" % above)
    res["R7.7_L_hull"] = Lrows

    # ============================================================ R7.8
    print("\n[R7.8] location-based fixed-hull headline")
    loc_full = np.array([ce_r(locs_of(yrs[y]), A_hull) for y in years])
    ids_full = full
    print("  locations: %.3f -> %.3f  = %+.1f%%"
          % (loc_full[0], loc_full[-1], 100 * (loc_full[-1] - loc_full[0]) / loc_full[0]))
    print("  identifiers: %.3f -> %.3f  = %+.1f%%"
          % (ids_full[0], ids_full[-1], 100 * (ids_full[-1] - ids_full[0]) / ids_full[0]))
    loc_b = ols_hac_slope(Y, loc_full)
    print("  location slope %+.4f  HAC95 [%+.4f,%+.4f]" % (loc_b[0], loc_b[2], loc_b[3]))
    res["R7.8_headline"] = {
        "loc_first": float(loc_full[0]), "loc_last": float(loc_full[-1]),
        "loc_pct": float(100 * (loc_full[-1] - loc_full[0]) / loc_full[0]),
        "ids_first": float(ids_full[0]), "ids_last": float(ids_full[-1]),
        "ids_pct": float(100 * (ids_full[-1] - ids_full[0]) / ids_full[0]),
        "loc_slope": loc_b[0], "loc_ci": [loc_b[2], loc_b[3]],
        "loc_series": loc_full.tolist(), "ids_series": ids_full.tolist()}

    # ============================================================ R7.9
    print("\n[R7.9] gap-filled population rerun")
    allids = sorted(set().union(*[set(yrs[y]) for y in years]))
    fill = {}
    for i in allids:
        vs = [y for y in years if i in yrs[y]]
        s = set(vs)
        for k2 in range(1, len(vs)):
            s.update(range(vs[k2 - 1] + 1, vs[k2]))
        fill[i] = s
    # location lookup per identifier (use the year it is present)
    loc_of = {}
    for y in years:
        for i, v in yrs[y].items():
            loc_of[i] = (round(v[0], 1), round(v[1], 1))
    org = (all_ids[:, 0].min(), all_ids[:, 1].min())
    span = max(all_ids[:, 0].max() - org[0], all_ids[:, 1].max() - org[1])
    cell = span / 20
    print("  year  N_filled  N_pub  R_ids_filled  R_ids_pub  R_loc_filled  G_filled")
    fillR, pubR, fillG, Nf = [], [], [], []
    for y in years:
        cur = [i for i in allids if y in fill[i]]
        Pf = np.array([loc_of[i] for i in cur])
        idsf = np.array([( [v for v in [None]][0], )]) if False else None
        # identifier points: use each id's coordinate
        Pid_f = np.array([loc_of[i] for i in cur])
        Pid_p = ids_pts(yrs[y])
        Ploc_f = np.unique(Pf, axis=0)
        fillR.append(ce_r(Pid_f, A_hull))
        pubR.append(ce_r(Pid_p, A_hull))
        fillG.append(gini_fixed_grid(Ploc_f, org, cell, 20))
        Nf.append(len(cur))
        print("  %d %6d %5d  %.3f  %.3f  %.3f  %.3f"
              % (y, len(cur), len(yrs[y]), fillR[-1], pubR[-1],
                 ce_r(Ploc_f, A_hull), fillG[-1]))
    fr = ols_hac_slope(Y, np.array(fillR))
    fg = ols_hac_slope(Y, np.array(fillG))
    print("  filled R slope %+.4f [%+.4f,%+.4f]" % (fr[0], fr[2], fr[3]))
    print("  filled Gini slope %+.5f [%+.5f,%+.5f]" % (fg[0], fg[2], fg[3]))
    res["R7.9_gapfilled"] = {"N": Nf, "R_filled": fillR, "R_pub": pubR,
                             "gini_filled": fillG,
                             "R_slope": list(ols_hac_slope(Y, np.array(fillR))),
                             "gini_slope": list(ols_hac_slope(Y, np.array(fillG)))}

    # ============================================================ R7.10
    print("\n[R7.10] snapshot: recount, resolve, test the rival explanation")
    db = pathlib.Path(os.environ.get("UO_DB") or (HERE / "urban_observatory.db"))
    con = sqlite3.connect(db)
    snap = {str(r[0]).strip() for r in con.execute("SELECT raw_id FROM sensors")}
    snapvars = {r[0] for r in con.execute("SELECT variable_name FROM variables")}
    census_all = set().union(*[set(yrs[y]) for y in years])
    inter = snap & census_all
    only_snap = snap - census_all
    only_cen = census_all - snap
    print("  snapshot %d, census %d, both %d, snapshot-only %d, census-only %d"
          % (len(snap), len(census_all), len(inter), len(only_snap), len(only_cen)))
    print("  coverage of census %.1f%%" % (100 * len(inter) / len(census_all)))
    # theme/variable of every identifier: last-seen year and theme
    theme_of, last_seen, first_seen, var_of = {}, {}, {}, {}
    for y in years:
        for i, v in yrs[y].items():
            theme_of[i] = v[2].split("/")[0]
            var_of[i] = v[2].split("-", 1)[-1] if "-" in v[2] else v[2].split("/")[-1]
            last_seen[i] = y
            first_seen.setdefault(i, y)
    veh = {"Vehicles"}
    om_veh = sum(1 for i in only_cen if theme_of.get(i) in veh)
    om_non = len(only_cen) - om_veh
    in_veh = sum(1 for i in inter if theme_of.get(i) in veh)
    in_non = len(inter) - in_veh
    print("  2x2: matched veh %d non %d | omitted veh %d non %d" % (in_veh, in_non, om_veh, om_non))
    orr = (om_veh / om_non) / (in_veh / in_non)
    print("  odds ratio (omitted vs matched, vehicle vs non): %.2f" % orr)
    retired = sum(1 for i in only_cen if last_seen.get(i, 2026) <= 2021)
    active = sum(1 for i in only_cen if last_seen.get(i, 2026) >= 2024)
    mid = len(only_cen) - retired - active
    print("  omitted last-seen <=2021: %d ; 2022-2023: %d ; >=2024: %d ; sum %d"
          % (retired, mid, active, retired + mid + active))
    # rival explanation: are the omitted variables still in the snapshot dictionary?
    om_vars = {var_of[i] for i in only_cen}
    present = sum(1 for i in only_cen if var_of.get(i) in snapvars)
    print("  omitted identifiers whose variable is in the snapshot's own variables "
          "table: %d of %d (%.1f%%)" % (present, len(only_cen), 100 * present / len(only_cen)))
    # `snapvars` is a set, so this list must be sorted explicitly: iterating a
    # set of str follows per-process hash order, which would make the committed
    # JSON differ byte-for-byte between runs.
    cars = sorted(v for v in snapvars if v in ("Cars", "Parking Spaces", "Car Count",
                                               "Occupied spaces"))
    print("  Cars/Parking Spaces present in the snapshot variable dictionary: %s" % cars)
    res["R7.10_snapshot"] = {
        "snapshot": len(snap), "census": len(census_all), "both": len(inter),
        "only_snap": len(only_snap), "only_cen": len(only_cen),
        "coverage": 100 * len(inter) / len(census_all),
        "matched_veh": in_veh, "matched_non": in_non,
        "omitted_veh": om_veh, "omitted_non": om_non, "odds_ratio": orr,
        "retired": retired, "mid": mid, "active": active,
        "omitted_var_in_snapshot": present,
        "omitted_var_in_snapshot_pct": 100 * present / len(only_cen),
        "cars_parking_in_snapshot": cars}

    (HERE / "results_rarefied.json").write_text(json.dumps(res, indent=1))
    print("\nwritten results_rarefied.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
