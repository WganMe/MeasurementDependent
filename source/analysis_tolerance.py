#!/usr/bin/env python3
"""Tolerance (near-duplicate) robustness: what the pre-submission board asked for.

WHY THIS EXISTS. analysis_neardup.py showed the headline fall in the Clark-Evans
index collapses from 45% to 4.3% once co-located registrations are merged at
25 m. That result is reported, but three things that depend on it were never
done:

  1. The tolerance was asserted, not justified. There is no nearest-neighbour
     distance distribution, no coordinate-precision audit, and no sweep, so
     "well below the spacing between distinct installations" has no evidence
     behind it and the reader cannot see that 5 m gives p = 0.053 while 25 m
     gives p = 0.74.

  2. The claim that the multiscale function L "is invariant to that merging" was
     never tested. K IS invariant to independent random thinning -- removing
     points at random leaves K unbiased. Tolerance deduplication is not random
     thinning: it removes exactly the closest pairs, so it changes K at every
     radius above the tolerance. This script tests the claim directly instead of
     asserting it.

  3. The merge is single-linkage, which can chain a row of sensors into one
     "site". No cluster-diameter distribution was reported, so chaining was
     neither shown nor excluded.

Also supplies the share/surplus decomposition §2.2 itself warns about, and
reconciles the exact-coordinate control row with the published location series
(they differ only in rounding: mm in analysis_neardup.py, 0.1 m in
analysis_multiscale.py).

Writes: results_tolerance.json

Usage: python3 analysis_tolerance.py
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np
from scipy.cluster import hierarchy
from scipy.spatial import ConvexHull, cKDTree
from scipy import stats

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analysis_common import load_years, ce_r  # noqa: E402
from analysis_multiscale import (  # noqa: E402
    RS, hull_edges, inward_lines, eroded_contains, L_border, ids_of,
)

HERE = pathlib.Path(__file__).resolve().parent
RNG = np.random.default_rng(20261005)

# The published series dedups at 0.1 m (analysis_multiscale.locs_of); the
# neardup control used mm. Sweep the rounding so the two are reconcilable.
ROUNDINGS_DECIMAL = [3, 2, 1, 0]
TOLS = [1.0, 2.0, 5.0, 10.0, 15.0, 25.0, 50.0]
PRIMARY_TOL = 25.0
ALT_TOL = 10.0


# ------------------------------------------------------------------ clustering
def labels_single(P: np.ndarray, r: float) -> np.ndarray:
    """Single-linkage: connected components of the r-graph (what neardup does)."""
    n = len(P)
    parent = np.arange(n)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, j in cKDTree(P).query_pairs(r, output_type="ndarray"):
        ri, rj = find(int(i)), find(int(j))
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)
    return np.array([find(i) for i in range(n)])


def labels_complete(P: np.ndarray, r: float) -> np.ndarray:
    """Complete-linkage: clusters whose maximum pairwise diameter is <= r."""
    if len(P) < 2:
        return np.zeros(len(P), int)
    z = hierarchy.linkage(P, method="complete")
    return hierarchy.fcluster(z, t=r, criterion="distance") - 1


def cluster_diameters(P: np.ndarray, lab: np.ndarray) -> list[float]:
    """Maximum pairwise distance inside each cluster (>1 point).

    Uses the convex hull when it is non-degenerate (fast for big chained
    clusters) and falls back to brute force when every point is collinear,
    which single-linkage on a row of sensors produces routinely.
    """
    out = []
    for c in np.unique(lab):
        Q = P[lab == c]
        if len(Q) < 2:
            continue
        if len(Q) == 2:
            out.append(float(np.linalg.norm(Q[0] - Q[1])))
            continue
        try:
            V = Q[ConvexHull(Q).vertices]
        except Exception:
            V = Q
        out.append(float(max(np.linalg.norm(V[i] - V[j])
                             for i in range(len(V)) for j in range(i + 1, len(V)))))
    return out


def low_range_gap(P: np.ndarray, hi: float) -> tuple[float, float, float]:
    """Largest gap in the sorted nearest-neighbour distances BELOW `hi`.

    This is the quantity that would justify a tolerance: a trough separating a
    co-located population from distinct installations. The largest gap over the
    whole range is always kilometres wide and says nothing about 25 m.
    """
    d = np.sort(cKDTree(P).query(P, k=2)[0][:, 1])
    d = d[(d > 0) & (d < hi)]
    if len(d) < 3:
        return (float("nan"), float("nan"), 0.0)
    dd = np.diff(d)
    k = int(np.argmax(dd))
    return float(d[k]), float(d[k + 1]), float(dd[k])


def centroids(P: np.ndarray, lab: np.ndarray) -> np.ndarray:
    return np.array([P[lab == c].mean(axis=0) for c in np.unique(lab)])


def reps_first(P: np.ndarray, lab: np.ndarray) -> np.ndarray:
    """One identifier per cluster: the first one encountered (neardup's rule)."""
    return P[np.sort(np.unique(lab, return_index=True)[1])]


def grid_snap(P: np.ndarray, r: float) -> np.ndarray:
    return np.unique(np.round(P / r) * r, axis=0)


# ---------------------------------------------------------------------- slopes
def ols_trend(years, vals):
    x = np.asarray(years, float)
    y = np.asarray(vals, float)
    keep = np.isfinite(y)
    x, y = x[keep], y[keep]
    b = np.polyfit(x, y, 1)
    resid = y - np.polyval(b, x)
    n = len(x)
    se = float(np.sqrt(np.sum(resid ** 2) / (n - 2) / np.sum((x - x.mean()) ** 2)))
    p = float(2 * stats.t.sf(abs(b[0] / se), n - 2))
    return float(b[0]), se, p


def fall_pct(a, b):
    return 100.0 * (a - b) / a


# ------------------------------------------------------------------------- main
def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    allP = np.vstack([ids_of(yrs[y]) for y in years])
    poly, A_hull = hull_edges(allP)
    lines = inward_lines(poly)
    res: dict = {"hull_area_m2": float(A_hull), "rs": RS.tolist(),
                 "tolerances_m": TOLS, "primary_tol_m": PRIMARY_TOL,
                 "alt_tol_m": ALT_TOL}

    # =========================================================== 1. JUSTIFY TOL
    print("=" * 78)
    print("[1] JUSTIFYING THE TOLERANCE")
    print("=" * 78)

    # 1a. coordinate precision in the archive
    lonlat = []
    for y in years:
        for v in idx["years"][str(y)]["identifiers"].values():
            if v[0] is not None and v[1] is not None:
                lonlat.append((v[0], v[1]))
    lonlat = np.array(lonlat, float)
    dec = []
    for row in lonlat[:20000]:
        for comp in row:
            s = repr(float(comp))
            dec.append(len(s.split(".")[1].rstrip("0")) if "." in s else 0)
    dec = np.array(dec)
    uniq_exact = len(np.unique(lonlat, axis=0))
    prec = {"n_coordinate_records": int(len(lonlat)),
            "distinct_exact": int(uniq_exact),
            "decimals_histogram": {int(k): int(v) for k, v in
                                   zip(*np.unique(dec, return_counts=True))}}
    print("  coordinate records: %d, distinct exact: %d"
          % (len(lonlat), uniq_exact))
    print("  decimal places histogram: "
          + ", ".join("%d dp: %d" % (k, v) for k, v in
                      sorted(prec["decimals_histogram"].items())))
    res["coordinate_precision"] = prec

    # 1b. nearest-neighbour distance distribution, pooled and by year
    print("\n  nearest-neighbour distances (m), pooled and by year")
    def nn_dist(P):
        if len(P) < 2:
            return np.array([])
        return cKDTree(P).query(P, k=2)[0][:, 1]

    nnp = nn_dist(allP)
    qs = [0, 1, 5, 10, 25, 50, 75, 90, 95, 99, 100]
    # Pooling the raw records is meaningless for spatial structure: the same
    # identifier recurs in every year it was active, so its own coordinates
    # become its nearest neighbour at 0 m. Report the repetition as an archive
    # fact, then take the NN distribution on the pooled DISTINCT coordinates.
    rep = {"records_pooled": int(len(allP)),
           "distinct_coordinates": int(len(np.unique(np.round(allP, 1), axis=0))),
           "pct_records_coincident": float(100 * (1 - len(np.unique(np.round(allP, 1), axis=0)) / max(len(allP), 1)))}
    print("  pooled records: %d, distinct coordinates: %d (%.1f%% of records are "
          "a repeat of an earlier year's coordinate for the same identifier)"
          % (rep["records_pooled"], rep["distinct_coordinates"],
             rep["pct_records_coincident"]))
    res["pooled_repetition"] = rep

    allP_u = np.unique(np.round(allP, 1), axis=0)
    nnp = nn_dist(allP_u)
    print("  NN on the %d distinct coordinates:" % len(allP_u))
    pooled_q = {str(q): float(np.percentile(nnp, q)) for q in qs}
    print("   pooled  n=%5d  " % len(allP_u)
          + "  ".join("%d%%=%.1f" % (q, np.percentile(nnp, q)) for q in qs))
    res["nn_pooled_percentiles"] = pooled_q

    nn_rows = []
    for y in years:
        d = nn_dist(ids_of(yrs[y]))
        nn_rows.append({"year": y, "n": int(len(d)),
                        "min": float(d.min()), "p25": float(np.percentile(d, 25)),
                        "median": float(np.median(d)),
                        "pct_within_25m": float(100 * np.mean(d < PRIMARY_TOL)),
                        "pct_within_10m": float(100 * np.mean(d < ALT_TOL))})
        print("   %d  n=%4d  min=%7.2f  p25=%8.1f  med=%9.1f  <10m=%5.1f%%  <25m=%5.1f%%"
              % (y, len(d), d.min(), np.percentile(d, 25), np.median(d),
                 100 * np.mean(d < ALT_TOL), 100 * np.mean(d < PRIMARY_TOL)))
    res["nn_by_year"] = nn_rows

    # is there a gap between the co-located population and the rest?
    gaps = []
    for y in years:
        d = np.sort(nn_dist(ids_of(yrs[y])))
        d = d[d > 0]
        if len(d) < 10:
            continue
        dd = np.diff(d)
        k = int(np.argmax(dd))
        gaps.append({"year": y, "gap_lower_m": float(d[k]),
                     "gap_upper_m": float(d[k + 1]), "gap_m": float(dd[k])})
    res["nn_gap_by_year"] = gaps
    print("  largest gap in the sorted NN distances, by year "
          "(where a co-located population would separate from distinct sites):")
    for g in gaps:
        print("   %d  gap between %.2f m and %.2f m  (width %.2f m)"
              % (g["year"], g["gap_lower_m"], g["gap_upper_m"], g["gap_m"]))

    # The gap that would actually justify a tolerance has to lie in the range
    # where the merge is doing work, not out at kilometres.
    print("\n  largest gap BELOW 200 m -- the only range that can justify a "
          "tolerance in metres:")
    low = []
    for y in years:
        a, b, w = low_range_gap(ids_of(yrs[y]), 200.0)
        low.append({"year": y, "lo": a, "hi": b, "width": w})
        print("   %d  gap between %6.2f m and %6.2f m  (width %5.2f m)"
              % (y, a, b, w))
    res["nn_low_gap_by_year"] = low
    print("  -> a tolerance is only justified where these gaps sit; note the "
          "shares below show a continuum, not two populations.")

    # 1c. the tolerance sweep
    print("\n  tolerance sweep (single-linkage, first identifier kept)")
    sweep = []
    for r in TOLS:
        rr, pp, vals = [], None, []
        for y in years:
            P = reps_first(ids_of(yrs[y]), labels_single(ids_of(yrs[y]), r))
            vals.append(ce_r(P, A_hull))
        s, se, p = ols_trend(years, vals)
        f = fall_pct(vals[0], vals[-1])
        sweep.append({"tol_m": r, "slope": s, "se": se, "p": p,
                      "fall_pct": f, "R_first": vals[0], "R_last": vals[-1]})
        print("   %5.1f m  R: %.3f -> %.3f  fall %5.1f%%  slope %+.5f  p = %.4f"
              % (r, vals[0], vals[-1], f, s, p))
    res["sweep"] = sweep

    # ==================================================== 2. MERGE ROBUSTNESS
    print("\n" + "=" * 78)
    print("[2] MERGE ROBUSTNESS")
    print("=" * 78)

    link_rows = []
    for r in (PRIMARY_TOL, ALT_TOL):
        for name, fn in (("single", labels_single), ("complete", labels_complete)):
            vals, merged, diams = [], 0, []
            for y in years:
                P = ids_of(yrs[y])
                lab = fn(P, r)
                vals.append(ce_r(reps_first(P, lab), A_hull))
                merged += len(P) - len(np.unique(lab))
                diams.extend(cluster_diameters(P, lab))
            s, se, p = ols_trend(years, vals)
            d = np.array(diams) if diams else np.array([0.0])
            link_rows.append({"tol_m": r, "linkage": name, "slope": s, "p": p,
                              "fall_pct": fall_pct(vals[0], vals[-1]),
                              "merged_total": int(merged),
                              "diam_median": float(np.median(d)),
                              "diam_p95": float(np.percentile(d, 95)),
                              "diam_max": float(d.max())})
            print("   %5.1f m  %-8s  fall %5.1f%%  p = %.4f  merged %5d  "
                  "cluster diameter median %.2f m, p95 %.1f m, max %.1f m"
                  % (r, name, fall_pct(vals[0], vals[-1]), p, merged,
                     np.median(d), np.percentile(d, 95), d.max()))

        # grid snapping and centroid choice at the primary tolerance
        for name, fn in (("grid-snap", grid_snap), ("centroid", centroids)):
            vals = []
            for y in years:
                P = ids_of(yrs[y])
                if name == "grid-snap":
                    Q = fn(P, r)
                else:
                    Q = fn(P, labels_single(P, r))
                vals.append(ce_r(Q, A_hull))
            s, se, p = ols_trend(years, vals)
            link_rows.append({"tol_m": r, "method": name, "slope": s, "p": p,
                              "fall_pct": fall_pct(vals[0], vals[-1])})
            print("   %5.1f m  %-8s  fall %5.1f%%  p = %.4f"
                  % (r, name, fall_pct(vals[0], vals[-1]), p))
    res["linkage"] = link_rows

    # ============================================== 3. SHARE, NOT SURPLUS (§2.2)
    print("\n" + "=" * 78)
    print("[3] SHARE vs SURPLUS (the distinction §2.2 warns about)")
    print("=" * 78)
    share_rows = []
    for y in years:
        P = ids_of(yrs[y])
        d = nn_dist(P)
        d = d[np.isfinite(d)]
        lab_x = np.unique(np.round(P, 1), axis=0, return_inverse=True)[1]
        lab_25 = labels_single(P, PRIMARY_TOL)
        n_ident = len(P)
        n_loc = len(np.unique(lab_x))
        n_site = len(np.unique(lab_25))
        share = int(np.sum(d < PRIMARY_TOL))          # identifiers with a neighbour
        surplus = n_ident - n_site                    # identifiers removed
        already = n_ident - n_loc                     # removed by exact dedup
        share_rows.append({"year": y, "identifiers": n_ident, "locations": n_loc,
                           "sites_25m": n_site, "share": share,
                           "surplus": surplus, "already_exact": already})
        print("   %d  ids %4d  loc %4d  sites@25m %4d  |  SHARE (has a neighbour "
              "<25m) %4d  |  SURPLUS (removed) %4d  (of which %d were already "
              "removed by exact dedup)"
              % (y, n_ident, n_loc, n_site, share, surplus, already))
    res["share_surplus"] = share_rows

    last = share_rows[-1]
    print("\n  2026: the abstract's \"306 of 706 identifiers\" is the SURPLUS "
          "(%d), not the SHARE (%d)."
          % (last["surplus"], last["share"]))
    res["share_surplus_2026"] = last

    # ================================================ 4. RECONCILE THE CONTROL
    print("\n" + "=" * 78)
    print("[4] RECONCILING THE EXACT-COORDINATE CONTROL ROW")
    print("=" * 78)
    rec = []
    for dp in ROUNDINGS_DECIMAL:
        vals = [ce_r(np.unique(np.round(ids_of(yrs[y]), dp), axis=0), A_hull)
                for y in years]
        s, se, p = ols_trend(years, vals)
        n26 = len(np.unique(np.round(ids_of(yrs[2026]), dp), axis=0))
        rec.append({"decimals": dp, "rounding_m": 10.0 ** (-dp),
                    "n_2026": n26, "R_first": vals[0], "R_last": vals[-1],
                    "fall_pct": fall_pct(vals[0], vals[-1]),
                    "slope": s, "p": p})
        print("   round to 1e-%d m (%g m):  2026 n=%3d  R %.4f -> %.4f  "
              "fall %5.2f%%  slope %+.5f  p = %.4f"
              % (dp, 10.0 ** (-dp), n26, vals[0], vals[-1],
                 fall_pct(vals[0], vals[-1]), s, p))
    res["rounding_reconciliation"] = rec
    print("  -> the neardup control row used 1e-3 (mm); the published series uses "
          "1e-1 (0.1 m).\n     The difference in the printed digits is that "
          "rounding, not a different analysis.")

    # ================================================= 5. L UNDER TOLERANCE
    print("\n" + "=" * 78)
    print("[5] THE 'L IS INVARIANT TO THAT MERGING' CLAIM, TESTED")
    print("=" * 78)
    try:
        ms = json.loads((HERE / "results_multiscale.json").read_text())
        env_lo = np.array(ms["L_locations"]["env_lo"])
        env_hi = np.array(ms["L_locations"]["env_hi"])
        have_env = True
        print("  reusing the published CSR envelope from results_multiscale.json")
    except Exception as e:                                   # pragma: no cover
        have_env = False
        print("  no published envelope available (%s)" % e)

    lres = {}
    for tag, tol in (("exact", 0.0), ("sites10", ALT_TOL), ("sites25", PRIMARY_TOL)):
        rows = []
        for y in years:
            P = ids_of(yrs[y])
            if tol <= 0:
                Q = np.unique(np.round(P, 1), axis=0)
            else:
                Q = reps_first(P, labels_single(P, tol))
            rows.append({"year": y, "n": int(len(Q)),
                         "L": [float(v) for v in L_border(Q, A_hull, lines=lines)]})
        arr = np.array([r["L"] for r in rows])
        trend = [ols_trend(years, arr[:, i]) for i in range(len(RS))]
        above = [int(np.sum(arr[:, i] > env_hi[i])) for i in range(len(RS))] \
            if have_env else None
        lres[tag] = {"rows": rows, "trend": [{"r": float(RS[i]), "slope": t[0],
                                              "p": t[2], "above_env_years": (above[i] if above else None)}
                                             for i, t in enumerate(trend)]}
        print("\n  L(r) on %s (n 2026 = %d)" % (tag, rows[-1]["n"]))
        print("   r (m)   " + " ".join("%8.0f" % v for v in RS))
        print("   2026    " + " ".join("%+8.1f" % v for v in arr[-1]))
        print("   2013    " + " ".join("%+8.1f" % v for v in arr[0]))
        print("   slope/yr" + " ".join("%+8.1f" % t[0] for t in trend))
        print("   p       " + " ".join("%8.3f" % t[2] for t in trend))
        if above:
            print("   above env (of 14)" + " ".join("%8d" % a for a in above))
    res["L_under_tolerance"] = lres

    # direct statement of the invariance claim at the scale the paper leads on
    print("\n  INVARIANCE TEST at 1 km:")
    for tag in ("exact", "sites10", "sites25"):
        t = [x for x in lres[tag]["trend"] if abs(x["r"] - 1000.0) < 1][0]
        print("   %-8s 2013 %+.1f  2026 %+.1f  slope %+.1f m/yr  p = %.4f"
              % (tag, lres[tag]["rows"][0]["L"][4], lres[tag]["rows"][-1]["L"][4],
                 t["slope"], t["p"]))
    print("  -> if these differ materially, 'invariant to that merging' is false "
          "as stated.")

    # 1 km trend with and without the two thin early years
    print("\n  1 km trend, with and without the thin early years:")
    for tag in ("exact", "sites10", "sites25"):
        rows = lres[tag]["rows"]
        for label, sel in (("all", range(14)), ("drop2013", range(1, 14)),
                           ("drop2013-14", range(2, 14))):
            ys = [rows[i]["year"] for i in sel]
            vs = [rows[i]["L"][4] for i in sel]
            s, se, p = ols_trend(ys, vs)
            print("   %-8s %-11s slope %+7.1f m/yr  p = %.3f" % (tag, label, s, p))

    (HERE / "results_tolerance.json").write_text(json.dumps(res, indent=1))
    print("\nwrote results_tolerance.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
