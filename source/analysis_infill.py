#!/usr/bin/env python3
"""
Infill-test analyses.

  A. infill test rerun against (i) the 5-95% core instead of the bounding box, and
     (ii) the previous year's own kernel density, and (iii) after excluding
     additions co-located within 10 m of an existing location.
  B. the rarefied Gini series with per-year intervals and a trend test.
  C. the saturating fit with a bootstrap interval on the floor, and AIC / LOOCV
     against the linear fit.
  D. turnover as an EXCESS over the growth benchmark, every year, plus a version
     that excludes identifiers whose absence spans one year or less.
  E. the 179 snapshot-only identifiers decomposed.
  F. the joint size/time model without 2017-2018 and with a fixed-b style
     small-sample correction.

Usage: python3 analysis_infill.py
Writes: results_infill.json
"""
from __future__ import annotations

import json
import math
import pathlib
import sqlite3
import sys
from collections import Counter

import numpy as np
from scipy.optimize import curve_fit
from scipy.spatial import cKDTree
from scipy.stats import norm

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from analysis_common import (  # noqa: E402
    DB, HERE, bbox, ce_r, gini_fixed_grid, load_years, ols_hac,
)

rng = np.random.default_rng(20260930)


def locs_of(d):
    return np.unique(np.round(np.array([(v[0], v[1]) for v in d.values()], float), 1), axis=0)


def core_rect(P):
    lo = np.percentile(P, 5, axis=0)
    hi = np.percentile(P, 95, axis=0)
    keep = ((P[:, 0] >= lo[0]) & (P[:, 0] <= hi[0]) &
            (P[:, 1] >= lo[1]) & (P[:, 1] <= hi[1]))
    return P[keep], float(hi[0] - lo[0]), float(hi[1] - lo[1])


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    res: dict = {"years": years}
    allP = np.array([(v[0], v[1]) for y in years for v in yrs[y].values()], float)
    org = (allP[:, 0].min(), allP[:, 1].min())
    span = max(allP[:, 0].max() - org[0], allP[:, 1].max() - org[1])

    # ------------------------------------------------------------------ A
    print("\n[A] infill test, three benchmarks and a co-location filter")
    rows = []
    prev_locs = prev_kde = None
    for y in years:
        Q = locs_of(yrs[y])
        if prev_locs is None:
            prev_locs = Q
            prev_kde = Q
            continue
        key = {tuple(r) for r in prev_locs}
        new = np.array([r for r in Q if tuple(r) not in key])
        # additions that are effectively co-located with an EXISTING location
        d_all, _ = cKDTree(prev_locs).query(new, k=1)
        not_colocated = new[d_all > 10.0]
        if len(new) == 0:
            prev_locs, prev_kde = Q, Q
            continue

        def bench(region, tree, pts):
            lo, hi = region.min(axis=0), region.max(axis=0)
            B = rng.uniform(lo, hi, size=(min(4000, max(500, 20 * len(pts))), 2))
            db, _ = tree.query(B, k=1)
            return float(np.median(db))

        # kernel-density benchmark: draw from the previous year's locations with
        # a bandwidth matched to the local spacing (median NN distance / 2)
        nn = cKDTree(prev_kde).query(prev_kde, k=2)[0][:, 1]
        bw = float(np.median(nn)) / 2.0
        KD = prev_kde[rng.integers(0, len(prev_kde), size=4000)]
        KD = KD + rng.normal(0.0, bw, size=KD.shape)
        dkd, _ = cKDTree(prev_kde).query(KD, k=1)

        core_prev, _, _ = core_rect(prev_locs)
        row = {
            "year": y, "n_new": int(len(new)),
            "n_new_not_colocated": int(len(not_colocated)),
            "median_new_to_prev_m": float(np.median(d_all)),
            "ratio_box": float(np.median(d_all) / bench(Q, cKDTree(prev_locs), new)),
            "ratio_core": float(np.median(d_all) / bench(core_prev, cKDTree(prev_locs), new)),
            "ratio_kde": float(np.median(d_all) / np.median(dkd)),
        }
        if len(not_colocated) > 2:
            d2, _ = cKDTree(prev_locs).query(not_colocated, k=1)
            row["median_not_colocated_m"] = float(np.median(d2))
            row["ratio_core_not_colocated"] = float(
                np.median(d2) / bench(core_prev, cKDTree(prev_locs), not_colocated))
            row["ratio_kde_not_colocated"] = float(np.median(d2) / np.median(dkd))
        rows.append(row)
        print("  %d new=%-4d (non-coloc %-4d) median %6.0f m | box %.2f core %.2f kde %.2f"
              % (y, row["n_new"], row["n_new_not_colocated"], row["median_new_to_prev_m"],
                 row["ratio_box"], row["ratio_core"], row["ratio_kde"]))
        prev_locs, prev_kde = Q, Q
    res["A_infill"] = rows

    # ------------------------------------------------------------------ B
    print("\n[B] rarefied Gini, every year, with intervals and a trend test")
    NMIN = 39
    B_rows = []
    for y in years:
        P = locs_of(yrs[y])
        vals = []
        for _ in range(1000):
            sub = P[rng.choice(len(P), size=min(NMIN, len(P)), replace=False)]
            g = gini_fixed_grid(sub, org, span / 20.0, 20)
            if np.isfinite(g):
                vals.append(g)
        B_rows.append({"year": y, "n": int(len(P)),
                       "mean": float(np.mean(vals)),
                       "ci": [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))],
                       "raw": float(gini_fixed_grid(P, org, span / 20.0, 20))})
        print("  %d rarefied %.3f [%.3f, %.3f]  raw %.3f"
              % (y, B_rows[-1]["mean"], B_rows[-1]["ci"][0], B_rows[-1]["ci"][1],
                 B_rows[-1]["raw"]))
    gm = np.array([r["mean"] for r in B_rows])
    Y = np.array(years, float)
    Xl = np.column_stack([np.ones_like(Y), Y])
    bl, *_ = np.linalg.lstsq(Xl, gm, rcond=None)
    pl = Xl @ bl
    r2l = 1 - ((gm - pl) ** 2).sum() / ((gm - gm.mean()) ** 2).sum()
    # Theil-Sen on the rarefied means
    slopes = [ (gm[j]-gm[i])/(Y[j]-Y[i]) for i in range(len(Y)) for j in range(i+1, len(Y)) ]
    res["B_rarefied"] = B_rows
    res["B_trend"] = {"slope": float(bl[1]), "r2": float(r2l),
                      "theil_sen_median_slope": float(np.median(slopes)),
                      "theil_sen_ci": [float(np.percentile(slopes, 2.5)),
                                       float(np.percentile(slopes, 97.5))],
                      "raw_slope": float(np.polyfit(Y, [r["raw"] for r in B_rows], 1)[0])}
    print("  rarefied slope %+.4f (R2 %.3f), Theil-Sen %+.4f [%+.4f, %+.4f]"
          % (bl[1], r2l, np.median(slopes), np.percentile(slopes, 2.5),
             np.percentile(slopes, 97.5)))
    print("  raw slope for comparison %+.4f"
          % np.polyfit(Y, [r["raw"] for r in B_rows], 1)[0])

    # ------------------------------------------------------------------ C
    print("\n[C] saturating fit: floor interval, AIC, leave-one-out error")
    Rl = np.array([ce_r(locs_of(yrs[y]), bbox(locs_of(yrs[y]))) for y in years])

    def sat(x, a, b, c):
        return a + b * np.exp(-c * (x - x.min()))

    popt, pcov = curve_fit(sat, Y, Rl, p0=[0.25, 0.5, 0.2], maxfev=40000)
    # bootstrap the floor
    boots = []
    for _ in range(2000):
        i = rng.integers(0, len(Y), len(Y))
        try:
            p, _ = curve_fit(sat, Y[i], Rl[i], p0=popt, maxfev=20000)
            boots.append(p[0])
        except Exception:
            pass
    boots = np.array(boots)
    # AIC on Gaussian errors
    def aicc(y, yhat, k):
        n = len(y)
        rss = ((y - yhat) ** 2).sum()
        aic = n * math.log(rss / n) + 2 * k
        return aic + (2 * k * (k + 1)) / (n - k - 1)
    # Both models must be compared on the SAME series. Earlier this compared the
    # saturating fit on the raw location series against a line fitted to the
    # RAREFIED series, which is not a model comparison at all. Fit the line to the
    # raw location series here so AICc and LOOCV are like for like.
    bl_raw, *_ = np.linalg.lstsq(Xl, Rl, rcond=None)
    lin_pred = Xl @ bl_raw
    sat_pred = sat(Y, *popt)
    # leave-one-out RMSE
    loo_lin, loo_sat = [], []
    for i in range(len(Y)):
        m = np.ones(len(Y), bool); m[i] = False
        b_i, *_ = np.linalg.lstsq(Xl[m], Rl[m], rcond=None)
        loo_lin.append(Rl[i] - Xl[i] @ b_i)
        try:
            p_i, _ = curve_fit(sat, Y[m], Rl[m], p0=popt, maxfev=20000)
            loo_sat.append(Rl[i] - sat(Y[i], *p_i))
        except Exception:
            loo_sat.append(np.nan)
    r2s = 1 - ((Rl - sat_pred) ** 2).sum() / ((Rl - Rl.mean()) ** 2).sum()
    post = Y >= 2020
    Xp = np.column_stack([np.ones(post.sum()), Y[post]])
    bp, sp, r2p, _ = ols_hac(Rl[post], Xp, 1)
    res["C_saturating"] = {
        "params": {"a": float(popt[0]), "b": float(popt[1]), "c": float(popt[2])},
        "floor_ci": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
        "r2_saturating": float(r2s),
        "r2_linear_on_raw": float(1 - ((Rl - lin_pred) ** 2).sum() / ((Rl - Rl.mean()) ** 2).sum()),
        "r2_linear_on_rarefied": float(r2l),
        "aicc_saturating": float(aicc(Rl, sat_pred, 3)),
        "aicc_linear": float(aicc(Rl, lin_pred, 2)),
        "loocv_rmse_saturating": float(np.nanmean(np.array(loo_sat) ** 2) ** 0.5),
        "loocv_rmse_linear": float(np.mean(np.array(loo_lin) ** 2) ** 0.5),
        "post2020_slope": float(bp[1]), "post2020_se": float(sp[1]), "post2020_r2": float(r2p),
        "n_post2020": int(post.sum()),
    }
    c = res["C_saturating"]
    print("  floor a = %.3f [%.3f, %.3f]" % (popt[0], c["floor_ci"][0], c["floor_ci"][1]))
    print("  R2 sat %.3f vs lin(raw) %.3f | AICc sat %.1f vs lin %.1f | LOOCV RMSE %.4f vs %.4f"
          % (r2s, c["r2_linear_on_raw"], c["aicc_saturating"], c["aicc_linear"],
             c["loocv_rmse_saturating"], c["loocv_rmse_linear"]))
    print("  post-2020 slope %+.4f (se %.4f), n=%d" % (bp[1], sp[1], post.sum()))

    # ------------------------------------------------------------------ D
    print("\n[D] turnover as EXCESS over benchmark, and a short-gap exclusion")
    def turnover(mode):
        """mode='all'        -> every identifier
        mode='no_short_gap' -> drop identifiers whose only interruptions are one
                               year long (temporary silences that manufacture an
                               exit and an entry pair each)
        mode='continuous'   -> keep only identifiers present in every year
        An earlier version of this filter was inverted: it kept only identifiers
        with gaps of two years or more, which left as few as one identifier in a
        year. The three modes above are the ones the text describes."""
        per_id = {i: [y for y in years if i in yrs[y]]
                  for i in set().union(*[set(yrs[y]) for y in years])}

        def maxgap(ys_i):
            return max([ys_i[k] - ys_i[k - 1] - 1 for k in range(1, len(ys_i))] or [0])

        if mode == "all":
            keep = set(per_id)
        elif mode == "no_short_gap":
            keep = {i for i, v in per_id.items() if maxgap(v) != 1}
        else:
            keep = {i for i, v in per_id.items() if maxgap(v) == 0}
        out = []
        prev = None
        for y in years:
            cur = set(yrs[y]) & keep
            if prev is not None:
                inn, ot = len(cur - prev), len(prev - cur)
                n = len(cur)
                turn = (inn + ot) / (2.0 * n) if n else 0.0
                gr = abs(n - len(prev)) / (2.0 * n) if n else 0.0
                out.append({"year": y, "n": n, "in": inn, "out": ot,
                            "turnover": turn, "growth_only": gr,
                            "excess": turn - gr, "ratio": turn / gr if gr > 0 else None})
            prev = cur
        return out, len(keep)
        out = []
        prev = None
        for y in years:
            cur = set(yrs[y]) & keep
            if prev is not None:
                inn, ot = len(cur - prev), len(prev - cur)
                n = len(cur)
                turn = (inn + ot) / (2.0 * n)
                gr = abs(n - len(prev)) / (2.0 * n)
                out.append({"year": y, "n": n, "in": inn, "out": ot,
                            "turnover": turn, "growth_only": gr,
                            "excess": turn - gr, "ratio": turn / gr if gr > 0 else None})
            prev = cur
        return out
    D_all, k_all = turnover("all")
    D_short, k_short = turnover("no_short_gap")
    D_cont, k_cont = turnover("continuous")
    res["D_turnover_all"] = D_all
    res["D_turnover_no_short_gap"] = D_short
    res["D_turnover_continuous"] = D_cont
    res["D_kept"] = {"all": k_all, "no_short_gap": k_short, "continuous": k_cont}
    print("  year   N   in  out  turnover  benchmark  excess   (all identifiers)")
    for r in D_all:
        print("  %d %5d %4d %4d   %.3f     %.3f    %+.3f" % (r["year"], r["n"], r["in"], r["out"],
              r["turnover"], r["growth_only"], r["excess"]))
    print("  excluding identifiers whose only gaps are one year (kept %d of %d):"
          % (k_short, k_all))
    for r in D_short:
        print("  %d %5d %4d %4d   %.3f     %.3f    %+.3f" % (r["year"], r["n"], r["in"], r["out"],
              r["turnover"], r["growth_only"], r["excess"]))
    print("  continuously present only (kept %d):" % k_cont)
    for r in D_cont:
        print("  %d %5d %4d %4d   %.3f     %.3f    %+.3f" % (r["year"], r["n"], r["in"], r["out"],
              r["turnover"], r["growth_only"], r["excess"]))
    res["D_summary"] = {
        "kept": {"all": k_all, "no_short_gap": k_short, "continuous": k_cont},
        "all_median_excess": float(np.median([r["excess"] for r in D_all])),
        "all_min_excess": float(np.min([r["excess"] for r in D_all])),
        "all_max_excess": float(np.max([r["excess"] for r in D_all])),
        "no_short_gap_median_excess": float(np.median([r["excess"] for r in D_short])),
        "continuous_median_excess": float(np.median([r["excess"] for r in D_cont])),
        "all_excess_positive_every_year": bool(all(r["excess"] > 0 for r in D_all)),
        "n_ratio_explodes": int(sum(1 for r in D_all if (r["ratio"] or 0) > 10)),
    }

    # ------------------------------------------------------------------ E
    print("\n[E] the 179 snapshot-only identifiers")
    con = sqlite3.connect(DB)
    snap = {str(r[0]).strip() for r in con.execute("SELECT raw_id FROM sensors") if r[0]}
    con.close()
    all_ids = {i for y in years for i in yrs[y]}
    snap_only = snap - all_ids
    raw_index = set()
    for y in years:
        raw_index |= set(idx["years"][str(y)]["identifiers"])
    dropped7 = raw_index - all_ids
    print("  snapshot-only total            : %d" % len(snap_only))
    print("  ... among the 7 dropped by the 60 km filter: %d" % len(snap_only & dropped7))
    print("  ... present in the archive index at all    : %d" % len(snap_only & raw_index))
    print("  ... in no archive index year (API-only+)   : %d" % len(snap_only - raw_index))
    res["E_snap_only"] = {
        "total": len(snap_only), "dropped_by_filter": len(snap_only & dropped7),
        "in_index": len(snap_only & raw_index), "not_in_index": len(snap_only - raw_index),
    }

    # ------------------------------------------------------------------ F
    print("\n[F] joint model without 2017-2018, small-sample corrected")
    R_all = np.array([ce_r(np.array([(v[0], v[1]) for v in yrs[y].values()], float),
                          bbox(np.array([(v[0], v[1]) for v in yrs[y].values()], float)))
                      for y in years])
    Ns = np.array([len(yrs[y]) for y in years], float)

    def joint(sel, lag):
        m = np.array([sel(y) for y in years])
        L = np.log(R_all[m]); N = np.log(Ns[m]); T = Y[m]
        X = np.column_stack([np.ones_like(N), N, T])
        b, s, r2, resid = ols_hac(L, X, lag)
        return {"coef_lnN": float(b[1]), "se_lnN": float(s[1]),
                "coef_year": float(b[2]), "se_year": float(s[2]),
                "r2": float(r2), "n": int(m.sum())}
    res["F_joint"] = {
        "all_hac2": joint(lambda y: True, 2),
        "excl1718_hac2": joint(lambda y: y not in (2017, 2018), 2),
        "excl1718_hac1": joint(lambda y: y not in (2017, 2018), 1),
        "excl1718_hac0": joint(lambda y: y not in (2017, 2018), 0),
    }
    # fixed-b style: inflate the HAC(0) t by the q=1 factor for n=12 (roughly 1.3)
    base = res["F_joint"]["excl1718_hac0"]
    res["F_joint"]["fixed_b_note"] = {
        "coef_year": base["coef_year"],
        "se_year_hac0": base["se_year"],
        "se_year_inflated_1.3": base["se_year"] * 1.3,
    }
    for k, v in res["F_joint"].items():
        if isinstance(v, dict) and "coef_lnN" in v:
            print("  %-18s lnN %+.3f (se %.3f)  year %+.4f (se %.4f)  R2 %.3f n=%d"
                  % (k, v["coef_lnN"], v["se_lnN"], v["coef_year"], v["se_year"], v["r2"], v["n"]))

    (HERE / "results_infill.json").write_text(json.dumps(res, indent=1))
    print("\nwritten results_infill.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
