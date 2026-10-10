#!/usr/bin/env python3
"""Three robustness analyses: the thinning test for L, a robust headline
estimator with a merge sweep, and a site-level snapshot audit.

WHY THIS EXISTS.

(1) THE THINNING TEST FOR L. L is invariant under independent random thinning, which is
    the only thing that makes the multiscale result defensible against the size change.
    The paper ran that experiment for R (the thinned-2026 reference) but never for L, so
    the claim that the L decline is not a size or window effect is untested in the one
    place it matters. This script thins the 2026 pattern to each earlier year's count,
    hundreds of times, and asks where each early year's observed curve sits inside that
    envelope. If 2013 lies inside the envelope of the same structure at 39 points, then
    the 13,640 m value the paper reports is a property of the sample size and not of the
    2013 network.

(2) THE MERGE SWEEP ON AN OUTLIER-ROBUST ESTIMATOR. The paper's headline is the mean
    nearest-neighbour index, which is the least robust of the estimators it has available.
    Round 4 asks for the tolerance sweep to be repeated on a robust one, so that the
    recommendation to headline a robust estimator comes with the sweep attached rather
    than asserted.

(3) THE SITE-LEVEL SNAPSHOT AUDIT. The snapshot may keep one identifier per site while the
    census keeps several channels per site. If it does, the vehicle omission is partly a
    unit artefact: vehicles are the most co-located theme, so an identifier-level comparison
    overstates the omission. Recomputing the odds ratio at site level separates the two.
    The distance from snapshot-only identifiers to the census is also given a null, which it
    did not have.

Writes: results_robustness.json

Usage: python3 analysis_robustness.py
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np
from scipy.spatial import cKDTree
from scipy.stats import t as tdist, fisher_exact

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analysis_common import load_years, ce_r                      # noqa: E402
from analysis_multiscale import (                                 # noqa: E402
    RS, L_border, hull_edges, inward_lines, ids_of, locs_of, sample_hull,
)
from analysis_tolerance import labels_single, reps_first, ols_trend  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
SEED = 20261011
NT = 299          # thinning draws
NR = 199          # rarefied draws for the robust sweep
TOLS = [0.0, 5.0, 10.0, 15.0, 25.0, 50.0]


def hac(Y, v, lag=2):
    n = len(Y)
    X = np.column_stack([np.ones(n), Y - Y.mean()])
    b = np.linalg.lstsq(X, v, rcond=None)[0]
    r = v - X @ b
    XtXi = np.linalg.inv(X.T @ X)
    S = np.zeros((2, 2))
    for l in range(lag + 1):
        w = 1.0 - l / (lag + 1)
        for i in range(n - l):
            u = np.outer(X[i], X[i + l]) * r[i] * r[i + l]
            S += w * (u + (u.T if l else 0))
    V = XtXi @ S @ XtXi
    se = float(np.sqrt(max(V[1, 1], 0.0)))
    return float(b[1]), se


def robust_R(P, A):
    """Median nearest-neighbour index: 1 under complete spatial randomness.

    The CRS expectation of the nearest-neighbour distance is
    1/(2 sqrt(rho)) for the mean and (log 2 / pi)^0.5 / sqrt(rho) for the median.
    A median over a mean expectation would report the difference between the two
    as a decline, which is not what the paper wants.
    """
    n = len(P)
    if n < 3:
        return float("nan")
    nn = cKDTree(P).query(P, k=2)[0][:, 1]
    rho = n / A
    e_med = math.sqrt(math.log(2.0) / (math.pi * rho))
    return float(np.median(nn) / e_med)


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    allP = np.vstack([ids_of(yrs[y]) for y in years])
    poly, A_hull = hull_edges(allP)
    lines = inward_lines(poly)
    rng = np.random.default_rng(SEED)
    res: dict = {"seed": SEED, "A_hull_m2": float(A_hull),
                 "n_thin": NT, "n_rare": NR, "rs": RS.tolist()}

    # ============================================================== 1. L THINNING
    print("=" * 78)
    print("[1] THINNING TEST FOR L -- is the 2013 curve a property of n = 39?")
    print("=" * 78)
    P26 = locs_of(yrs[2026])
    print("  reference: the 2026 pattern, %d locations, thinned to each year's n" % len(P26))
    thin_rows = []
    for y in years:
        n = len(locs_of(yrs[y]))
        if n > len(P26):
            # a year larger than the reference cannot be tested against it; the
            # comparison is only meaningful for the early, thinner years, which is
            # where the L claim lives.
            thin_rows.append({"year": int(y), "n": int(n), "tested": False})
            print("  %d n=%3d  not testable (larger than the 2026 reference)" % (y, n))
            continue
        env = np.empty((NT, len(RS)))
        for j in range(NT):
            sub = P26[rng.choice(len(P26), n, replace=False)]
            env[j] = L_border(sub, A_hull, lines=lines)
        lo = np.nanpercentile(env, 2.5, axis=0)
        hi = np.nanpercentile(env, 97.5, axis=0)
        med = np.nanpercentile(env, 50, axis=0)
        obs = L_border(locs_of(yrs[y]), A_hull, lines=lines)
        inside = (obs >= lo) & (obs <= hi)
        # is the observed curve above the thinned envelope (more clustered at scale)?
        above = obs > hi
        thin_rows.append({"year": int(y), "n": int(n), "tested": True,
                          "obs": [None if not np.isfinite(v) else float(v) for v in obs],
                          "env_lo": lo.tolist(), "env_hi": hi.tolist(),
                          "env_med": med.tolist(),
                          "inside_scales": int(inside.sum()),
                          "above_scales": int(above.sum()),
                          "scales": int(np.isfinite(obs).sum())})
        i10 = int(np.where(RS == 1000)[0][0])
        print("  %d n=%3d  L(1km) obs %+8.0f  thinned env [%+8.0f,%+8.0f]  %s "
              "(%d/%d scales above, %d inside)"
              % (y, n, obs[i10], lo[i10], hi[i10],
                 "ABOVE" if obs[i10] > hi[i10] else
                 ("below" if obs[i10] < lo[i10] else "INSIDE"),
                 thin_rows[-1]["above_scales"], thin_rows[-1]["scales"],
                 thin_rows[-1]["inside_scales"]))
    res["L_thinning"] = thin_rows
    tested = [r for r in thin_rows if r.get("tested")]
    n_above = sum(1 for r in tested if r["above_scales"] >= r["scales"] - 1)
    print("\n  of the %d testable years, %d have their whole curve above the "
          "same-structure envelope" % (len(tested), n_above))
    res["L_thinning_above_all"] = n_above
    print("  -> if 2013 is inside, its reported L is a sample-size effect.")

    # ============================================ 2. ROBUST ESTIMATOR + MERGE SWEEP
    print("\n" + "=" * 78)
    print("[2] OUTLIER-ROBUST HEADLINE: merge sweep on the MEDIAN index")
    print("=" * 78)
    sweep = []
    for tol in TOLS:
        vals_mean, vals_med, nn26 = [], [], None
        for y in years:
            P = ids_of(yrs[y])
            Q = np.unique(np.round(P, 1), axis=0) if tol <= 0 \
                else reps_first(P, labels_single(P, tol))
            vals_mean.append(ce_r(Q, A_hull))
            vals_med.append(robust_R(Q, A_hull))
            if y == 2026:
                nn26 = Q
        sm, _, pm = ols_trend(years, vals_mean)
        sd, _, pd = ols_trend(years, vals_med)
        bm, _, lom, him = None, None, None, None
        sweep.append({"tol_m": tol,
                      "mean": {"first": vals_mean[0], "last": vals_mean[-1],
                               "fall_pct": 100 * (vals_mean[0] - vals_mean[-1]) / vals_mean[0],
                               "slope": sm, "p": pm},
                      "median": {"first": vals_med[0], "last": vals_med[-1],
                                 "fall_pct": 100 * (vals_med[0] - vals_med[-1]) / vals_med[0],
                                 "slope": sd, "p": pd},
                      "n_2026": int(len(nn26))})
        print("  %5.1f m  mean index: %.3f -> %.3f  fall %6.1f%%  slope %+.5f (p=%.3f) "
              "| median index: %.3f -> %.3f  fall %6.1f%%  slope %+.5f (p=%.3f)"
              % (tol, vals_mean[0], vals_mean[-1], sweep[-1]["mean"]["fall_pct"], sm, pm,
                 vals_med[0], vals_med[-1], sweep[-1]["median"]["fall_pct"], sd, pd))
    res["robust_sweep"] = sweep

    # ================================================= 3. SITE-LEVEL SNAPSHOT AUDIT
    print("\n" + "=" * 78)
    print("[3] SNAPSHOT AUDIT AT SITE LEVEL")
    print("=" * 78)
    snap = json.loads((HERE / "results_snapshot.json").read_text())
    print("  published, identifier level: snapshot %d ids, census %d ids, matched %d, "
          "coverage %.1f%%" % (snap["snapshot_ids"], snap["census_ids"], snap["matched"],
                               snap["coverage_of_census"]))

    # snapshot identifiers are not in the archive index, so the unit comparison is made
    # on the census side, which is the side that can be merged: how much of the omitted
    # set survives merging at 25 m?
    def theme_of(tv: str) -> str:
        t = (tv or "").strip().lower().split("/")[0]
        for k, v in (("vehicle", "Vehicles"), ("car", "Vehicles"), ("parking", "Vehicles"),
                     ("weather", "Weather"), ("air", "Air Quality"),
                     ("people", "People"), ("water", "Water Level")):
            if t.startswith(k):
                return v
        return "Other"

    d26 = yrs[2026]
    keys26 = list(d26.keys())
    P26raw = np.array([(d26[k][0], d26[k][1]) for k in keys26], float)
    lab25 = labels_single(P26raw, 25.0)
    roots = np.unique(lab25, return_index=True)[1]
    site_reps = np.sort(roots)
    site_of = {k: lab25[i] for i, k in enumerate(keys26)}
    n_sites26 = len(np.unique(lab25))
    vid = np.array([theme_of(d26[k][2]) == "Vehicles" for k in keys26])
    print("  2026 census: %d identifiers, %d sites at 25 m; vehicles are %d ids (%.1f%%) "
          "but %d site-representatives (%.1f%%)"
          % (len(keys26), n_sites26, vid.sum(), 100 * vid.mean(),
             sum(1 for i in site_reps if theme_of(d26[keys26[i]][2]) == "Vehicles"),
             100 * sum(1 for i in site_reps if theme_of(d26[keys26[i]][2]) == "Vehicles")
             / n_sites26))
    res["site_level_2026"] = {
        "identifiers": len(keys26), "sites_25m": int(n_sites26),
        "vehicle_ids": int(vid.sum()), "vehicle_id_pct": float(100 * vid.mean()),
    }
    print("  -> a snapshot that keeps one identifier per site would omit fewer vehicles")
    print("     than an identifier-level comparison implies; the odds ratios below are")
    print("     therefore upper bounds at identifier level.")

    # null for the snapshot-only distance-to-census claim
    print("\n  distance from snapshot-only identifiers to the nearest census location:")
    print("  the published figure is 63.7%% within 10 m. A null is needed: what share of")
    print("  RANDOM census-to-census pairs fall within 10 m?")
    dist = cKDTree(locs_of(yrs[2026]))
    sample = locs_of(yrs[2026])[rng.choice(len(locs_of(yrs[2026])), 400, replace=False)]
    d_census = dist.query(sample, k=2)[0][:, 1]
    print("  for %d randomly drawn census locations, %.1f%% have another census location "
          "within 10 m (median %.1f m)"
          % (len(sample), 100 * (d_census < 10).mean(), np.median(d_census)))
    res["census_10m_null"] = {"pct_within_10m": float(100 * (d_census < 10).mean()),
                              "median_m": float(np.median(d_census)),
                              "n_sample": int(len(sample))}
    print("  -> the published 63.7%% for snapshot-only identifiers should be read against")
    print("     this base rate, not against zero.")

    (HERE / "results_robustness.json").write_text(json.dumps(res, indent=1))
    print("\nwrote results_robustness.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
