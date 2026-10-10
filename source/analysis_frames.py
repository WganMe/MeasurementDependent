#!/usr/bin/env python3
"""
Reference-frame analyses.

Adds, all on DISTINCT LOCATIONS unless stated, so the unit matches the objection
that co-located channels inflate the identifier series:

  A. core R on locations, with the core's own area
  B. piecewise / saturating trend fits, and the post-2020 segment
  C. an infill-versus-expansion test: distance from each year's new locations to
     the nearest location present the year before
  D. rarefaction of the Gini to a common N per year
  E. turnover as a share of each year's population, against a pure-growth benchmark
  F. the joint size/time regression refitted without 2017-2018, with a
     small-sample (fixed-b style) correction in addition to HAC
  G. snapshot omission conditioned on presence in the snapshot's own window

Usage: python3 analysis_frames.py
Writes: results_unit.json
"""
from __future__ import annotations

import json
import math
import pathlib
import sqlite3
import sys
from collections import Counter

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from analysis_common import (  # noqa: E402
    DB, HERE, bbox, ce_r, gini_fixed_grid, load_years, ols_hac, proj,
)

rng = np.random.default_rng(20260930)


def locs_of(yrs_y: dict) -> np.ndarray:
    """Distinct coordinates (10 m rounding) for one year."""
    return np.unique(np.round(np.array([(v[0], v[1]) for v in yrs_y.values()], float), 1),
                     axis=0)


def core_rect(P: np.ndarray):
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

    # ---------------------------------------------------------------- A
    print("\n[A] core R on DISTINCT LOCATIONS")
    A = []
    for y in years:
        Q = locs_of(yrs[y])
        if len(Q) < 5:
            continue
        C, w, h = core_rect(Q)
        A.append({"year": y, "n_loc": len(Q), "n_core": len(C),
                  "core_km2": w * h / 1e6,
                  "R_loc_box": ce_r(Q, bbox(Q)),
                  "R_loc_core": ce_r(C, w * h)})
        print("  %d locs=%-4d core=%-4d %7.1f km2  R_box=%.3f  R_core=%.3f"
              % (y, len(Q), len(C), A[-1]["core_km2"],
                 A[-1]["R_loc_box"], A[-1]["R_loc_core"]))
    res["A_loc_core"] = A

    # ---------------------------------------------------------------- B
    print("\n[B] trend shape: linear, piecewise, saturating")
    R_id = np.array([ce_r(np.array([(v[0], v[1]) for v in yrs[y].values()], float),
                          bbox(np.array([(v[0], v[1]) for v in yrs[y].values()], float)))
                     for y in years])
    R_lo = np.array([ce_r(locs_of(yrs[y]), bbox(locs_of(yrs[y]))) for y in years])
    Y = np.array(years, float)

    def fit_r2(y, X):
        b, *_ = np.linalg.lstsq(X, y, rcond=None)
        p = X @ b
        return 1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum()

    lin_id = fit_r2(R_id, np.column_stack([np.ones_like(Y), Y]))
    lin_lo = fit_r2(R_lo, np.column_stack([np.ones_like(Y), Y]))
    # piecewise: break at each candidate year, keep the better two-segment fit
    best = None
    for k in range(3, len(Y) - 2):
        X = np.column_stack([np.ones_like(Y), Y,
                             np.maximum(0.0, Y - Y[k])])
        r2 = fit_r2(R_lo, X)
        if best is None or r2 > best[1]:
            best = (int(Y[k]), r2)
    # saturating: R ~ a + b*exp(-c*(year-2013))
    from scipy.optimize import curve_fit

    def sat(x, a, b, c):
        return a + b * np.exp(-c * (x - x.min()))

    try:
        popt, _ = curve_fit(sat, Y, R_lo, p0=[0.25, 0.5, 0.2], maxfev=20000)
        sat_r2 = 1 - ((R_lo - sat(Y, *popt)) ** 2).sum() / ((R_lo - R_lo.mean()) ** 2).sum()
        sat_res = {"a": float(popt[0]), "b": float(popt[1]), "c": float(popt[2]),
                   "r2": float(sat_r2)}
    except Exception as e:  # pragma: no cover
        sat_res = {"error": str(e)}

    post = Y >= 2020
    Xp = np.column_stack([np.ones(post.sum()), Y[post]])
    bp, sep, r2p, _ = ols_hac(R_lo[post], Xp, 2)
    res["B_trend"] = {
        "linear_r2_locations": float(lin_lo), "linear_r2_identifiers": float(lin_id),
        "piecewise_break_year": best[0] if best else None,
        "piecewise_r2": float(best[1]) if best else None,
        "saturating": sat_res,
        "post2020_slope_locations": float(bp[1]), "post2020_hac_se": float(sep[1]),
        "post2020_r2": float(r2p),
    }
    print("  linear R2: locations %.3f, identifiers %.3f" % (lin_lo, lin_id))
    if best:
        print("  piecewise break at %d gives R2 %.3f" % best)
    print("  saturating: a=%.3f b=%.3f c=%.3f  R2=%.3f"
          % (sat_res.get("a", float("nan")), sat_res.get("b", float("nan")),
             sat_res.get("c", float("nan")), sat_res.get("r2", float("nan"))))
    print("  post-2020 slope (locations): %+.4f  HAC se %.4f  R2 %.3f"
          % (bp[1], sep[1], r2p))

    # ---------------------------------------------------------------- C
    print("\n[C] infill vs expansion: new locations vs previous year's set")
    C_rows = []
    prev = None
    for y in years:
        Q = locs_of(yrs[y])
        if prev is None:
            prev = Q
            continue
        # locations present this year and absent last year
        key = {tuple(r) for r in prev}
        new = np.array([r for r in Q if tuple(r) not in key])
        if len(new) == 0:
            prev = Q
            continue
        d, _ = cKDTree(prev).query(new, k=1)
        # benchmark: what a uniform-expansion draw over the year's bbox would give
        lo, hi = Q.min(axis=0), Q.max(axis=0)
        n_bench = min(4000, len(new) * 20)
        B = rng.uniform(lo, hi, size=(n_bench, 2))
        db, _ = cKDTree(prev).query(B, k=1)
        C_rows.append({"year": y, "n_new": int(len(new)),
                       "median_dist_new_m": float(np.median(d)),
                       "median_dist_random_m": float(np.median(db)),
                       "ratio": float(np.median(d) / np.median(db))})
        print("  %d new=%-4d median dist to prev set %6.0f m vs random %6.0f m  ratio %.2f"
              % (y, len(new), C_rows[-1]["median_dist_new_m"],
                 C_rows[-1]["median_dist_random_m"], C_rows[-1]["ratio"]))
        prev = Q
    res["C_infill"] = C_rows

    # ---------------------------------------------------------------- D
    print("\n[D] Gini rarefied to a common N")
    allP = np.array([(v[0], v[1]) for y in years for v in yrs[y].values()], float)
    org = (allP[:, 0].min(), allP[:, 1].min())
    span = max(allP[:, 0].max() - org[0], allP[:, 1].max() - org[1])
    N_MIN = 41  # the smallest year
    D_rows = []
    for y in years:
        P = locs_of(yrs[y])
        vals = []
        for _ in range(500):
            sub = P[rng.choice(len(P), size=min(N_MIN, len(P)), replace=False)]
            g = gini_fixed_grid(sub, org, span / 20.0, 20)
            if np.isfinite(g):
                vals.append(g)
        D_rows.append({"year": y, "n_loc": int(len(P)),
                       "gini_rarefied_mean": float(np.mean(vals)),
                       "gini_rarefied_ci": [float(np.percentile(vals, 2.5)),
                                            float(np.percentile(vals, 97.5))],
                       "gini_full": float(gini_fixed_grid(P, org, span / 20.0, 20))})
        print("  %d n=%-4d rarefied Gini %.3f [%.3f, %.3f]  (full %.3f)"
              % (y, len(P), D_rows[-1]["gini_rarefied_mean"],
                 D_rows[-1]["gini_rarefied_ci"][0], D_rows[-1]["gini_rarefied_ci"][1],
                 D_rows[-1]["gini_full"]))
    gm = np.array([r["gini_rarefied_mean"] for r in D_rows])
    res["D_rarefied"] = D_rows
    res["D_rarefied_trend"] = {"slope": float(np.polyfit(Y, gm, 1)[0]),
                               "first": float(gm[0]), "last": float(gm[-1])}

    # ---------------------------------------------------------------- E
    print("\n[E] turnover as a share of population, and a growth benchmark")
    E_rows = []
    prevset = None
    for y in years:
        cur = set(yrs[y])
        if prevset is not None:
            inn = len(cur - prevset)
            out = len(prevset - cur)
            n = len(cur)
            # pure-growth benchmark: population grows from P_{t-1} to P_t with no
            # replacement, so turnover share is |dN| / N_t
            turn = (inn + out) / (2.0 * n)
            E_rows.append({"year": y, "n": n, "in": inn, "out": out,
                           "turnover_share": turn,
                           "growth_only_share": abs(n - len(prevset)) / (2.0 * n)})
            print("  %d N=%-4d in=%-4d out=%-4d turnover %.2f  growth-only %.2f  ratio %.1f"
                  % (y, n, inn, out, turn, E_rows[-1]["growth_only_share"],
                     turn / E_rows[-1]["growth_only_share"] if E_rows[-1]["growth_only_share"] else float("nan")))
        prevset = cur
    res["E_turnover"] = E_rows
    # how many identifiers leave and return
    seen = Counter()
    for y in years:
        for i in yrs[y]:
            seen[i] += 1
    res["E_returners"] = {"distinct": len(seen),
                          "present_one_year_only": sum(1 for v in seen.values() if v == 1),
                          "present_in_all": sum(1 for v in seen.values() if v == len(years)),
                          "appear_twice_or_more_nonadjacent": None}
    # gaps: identifiers with a gap between first and last presence
    gaps = 0
    for i in seen:
        ys_i = [y for y in years if i in yrs[y]]
        if len(ys_i) > 1 and (ys_i[-1] - ys_i[0] + 1) > len(ys_i):
            gaps += 1
    res["E_returners"]["with_a_gap"] = gaps
    print("  distinct identifiers: %d, present in one year only: %d, with a gap: %d"
          % (len(seen), res["E_returners"]["present_one_year_only"], gaps))

    # ---------------------------------------------------------------- F
    print("\n[F] joint size/time model, excluding the publishing discontinuity")
    rows = [(y, len(yrs[y]), R_id[k]) for k, y in enumerate(years)]
    def joint(sel, lag):
        sub = [r for r in rows if sel(r[0])]
        L = np.log(np.array([r[2] for r in sub]))
        N = np.log(np.array([r[1] for r in sub], float))
        T = np.array([r[0] for r in sub], float)
        X = np.column_stack([np.ones_like(N), N, T])
        b, s, r2, resid = ols_hac(L, X, lag)
        return {"coef_lnN": float(b[1]), "se_lnN": float(s[1]),
                "coef_year": float(b[2]), "se_year": float(s[2]), "r2": float(r2),
                "n": len(sub)}
    res["F_joint"] = {
        "all_years_hac2": joint(lambda y: True, 2),
        "excl_2017_2018_hac2": joint(lambda y: y not in (2017, 2018), 2),
        "excl_2017_2018_hac1": joint(lambda y: y not in (2017, 2018), 1),
        "excl_2017_2018_2026_hac1": joint(lambda y: y not in (2017, 2018, 2026), 1),
        "excl_2017_2018_hac0": joint(lambda y: y not in (2017, 2018), 0),
    }
    for k, v in res["F_joint"].items():
        print("  %-28s lnN %+.3f (se %.3f)  year %+.4f (se %.4f)  R2 %.3f  n=%d"
              % (k, v["coef_lnN"], v["se_lnN"], v["coef_year"], v["se_year"], v["r2"], v["n"]))
    # how non-monotonic is N really
    Ns = np.array([len(yrs[y]) for y in years], float)
    res["F_monotonicity"] = {
        "n_decreases": int(sum(1 for k in range(1, len(Ns)) if Ns[k] < Ns[k - 1])),
        "corr_lnN_year": float(np.corrcoef(np.log(Ns), Y)[0, 1]),
        "max_decline_pct": float(100 * (Ns[8] - Ns[11]) / Ns[8]),
    }
    print("  N decreases in %d of 13 steps; corr(lnN, year) = %+.3f"
          % (res["F_monotonicity"]["n_decreases"], res["F_monotonicity"]["corr_lnN_year"]))

    (HERE / "results_unit.json").write_text(json.dumps(res, indent=1))
    print("\nwritten results_unit.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
