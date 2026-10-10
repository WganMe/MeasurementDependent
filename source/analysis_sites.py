#!/usr/bin/env python3
"""Every spatial result that used exact-coordinate locations, recomputed on MERGED SITES.

WHY THIS EXISTS. analysis_neardup.py and analysis_tolerance.py showed that the paper's
headline falls from 45% to 4.3% once co-located registrations are merged at 25 m, and
that the merge tolerance is a choice the data do not identify. But only the Clark-Evans
series and the L curve were ever recomputed on the merged unit. Every other spatial
result in the paper -- the inhomogeneous null, the infill permutation envelope, the
leave-one-out intensity, the core sweep, the theme-stratified trends, the rarefaction,
the Gini and the new-to-new batch test -- is still computed on exact-coordinate
locations, which is the unit the paper itself has just shown to be unreliable for
registration reasons.

That is the asymmetry the pre-submission board named: the paper qualifies its headline
and then reports everything else on the unit it qualified. This script closes it by
recomputing each of those results on a merged "site" unit at two tolerances, with the
exact-coordinate value as the control so the two are directly comparable.

Sites are defined as in analysis_tolerance.py: single-linkage connected components of
the r-graph, keeping the first identifier encountered. The 10 m and 25 m tolerances are
used because they bracket the range over which the Clark-Evans result moves.

Every block prints its exact-coordinate control alongside the site values, so a reader
can see which conclusions are unit-dependent and which are not.

Writes: results_sites.json

Usage: python3 analysis_sites.py
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np
from scipy.spatial import cKDTree, ConvexHull
from scipy.stats import t as tdist

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analysis_common import load_years, ce_r, gini_fixed_grid  # noqa: E402
from analysis_multiscale import (                             # noqa: E402
    RS, L_border, hull_edges, inward_lines, ids_of, locs_of,
)
from analysis_tolerance import (                              # noqa: E402
    labels_single, reps_first, ols_trend,
)

HERE = pathlib.Path(__file__).resolve().parent
SEED = 20261007
TOLS = {"exact": 0.0, "site10": 10.0, "site25": 25.0}
BAND = 750.0
NNULL = 199
NPERM_RL = 199
NPERM_BATCH = 499
NRAKE = 200
THIN_2026 = 1000


# ------------------------------------------------------------------ unit helpers
def unit_of(d: dict, tol: float) -> np.ndarray:
    """The unit under test: exact coordinates, or merged sites at `tol`."""
    P = ids_of(d)
    if tol <= 0:
        return locs_of(d)
    return reps_first(P, labels_single(P, tol))


def units(yrs, years, tol):
    return {y: unit_of(yrs[y], tol) for y in years}


# --------------------------------------------------------------- shared kernels
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
    tc = tdist.ppf(0.975, n - 2)
    return float(b[1]), se, float(b[1] - tc * se), float(b[1] + tc * se)


def relabel_pairs(units_, years, nperm, rng):
    """Random-labelling test: are NEW locations further from the old ones than chance?

    The label permutation holds the pooled support and intensity fixed, which is what
    the exact-coordinate version of this test does.
    """
    rows = []
    for k in range(1, len(years)):
        prev, cur = units_[years[k - 1]], units_[years[k]]
        prevset = {tuple(p) for p in prev}
        new = np.array([p for p in cur if tuple(p) not in prevset])
        if len(new) < 3:
            continue
        pooled = np.vstack([prev, new])
        labels = np.array([0] * len(prev) + [1] * len(new))
        obs = float(np.median(cKDTree(prev).query(new, k=1)[0]))
        sims = np.empty(nperm)
        for j in range(nperm):
            lab = labels[rng.permutation(len(pooled))]
            t2 = cKDTree(pooled[lab == 0])
            sims[j] = np.median(t2.query(pooled[lab == 1], k=1)[0])
        lo, hi = np.percentile(sims, [2.5, 97.5])
        rows.append({"year": int(years[k]), "n_new": int(len(new)),
                     "obs_median_m": obs, "env_lo": float(lo), "env_hi": float(hi),
                     "p_low": float((sims <= obs).mean()),
                     "above": bool(obs > hi), "below": bool(obs < lo)})
    return rows


def batch_pairs(units_, years, nperm, rng):
    """New-to-new: are NEW locations clustered among themselves, vs pooled subsets?"""
    rows = []
    for k in range(1, len(years)):
        prev, cur = units_[years[k - 1]], units_[years[k]]
        prevset = {tuple(p) for p in prev}
        new = np.array([p for p in cur if tuple(p) not in prevset])
        if len(new) < 3:
            continue
        pooled = np.vstack([prev, new])
        obs = float(np.median(cKDTree(new).query(new, k=2)[0][:, 1]))
        sims = []
        for _ in range(nperm):
            sub = pooled[rng.choice(len(pooled), len(new), replace=False)]
            if len(sub) >= 3:
                sims.append(float(np.median(cKDTree(sub).query(sub, k=2)[0][:, 1])))
        lo, hi = np.percentile(sims, [2.5, 97.5])
        rows.append({"year": int(years[k]), "n_new": int(len(new)), "obs": obs,
                     "lo": float(lo), "hi": float(hi),
                     "clustered": bool(obs < lo)})
    return rows


# ------------------------------------------------------------------------ main
def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    rng = np.random.default_rng(SEED)

    allP = np.vstack([ids_of(yrs[y]) for y in years])
    poly, A_hull = hull_edges(allP)
    lines = inward_lines(poly)
    # the paper's Gini grid: origin at the minimum pooled coordinate, square span
    # covering the whole record, 20 cells per side (analysis_rarefy.py; the consolidation
    # script now lives in archive/_gini_consolidated.py)
    GINI_ORG = (float(allP[:, 0].min()), float(allP[:, 1].min()))
    GINI_SPAN = float(max(allP[:, 0].max() - GINI_ORG[0],
                          allP[:, 1].max() - GINI_ORG[1]))
    GINI_NX = 20
    GINI_CELL = GINI_SPAN / GINI_NX
    res: dict = {"seed": SEED, "A_hull_m2": float(A_hull),
                 "tolerances": {k: v for k, v in TOLS.items()},
                 "n_null": NNULL, "bandwidth_m": BAND, "rs": RS.tolist(),
                 "gini_grid": {"origin": GINI_ORG, "span_m": GINI_SPAN,
                               "cells": GINI_NX, "cell_m": GINI_CELL}}

    U = {tag: units(yrs, years, tol) for tag, tol in TOLS.items()}
    print("unit sizes (2026): " + ", ".join(
        "%s=%d" % (t, len(U[t][2026])) for t in TOLS))

    # ======================================================== 1. CONTROLS FIRST
    print("\n" + "=" * 78)
    print("[0] CONTROLS -- exact-coordinate values must reproduce the published ones")
    print("=" * 78)
    ctl = {}
    R_ex = np.array([ce_r(U["exact"][y], A_hull) for y in years])
    b, se, lo, hi = hac(np.array(years, float), R_ex)
    ctl["R_exact"] = {"first": float(R_ex[0]), "last": float(R_ex[-1]),
                      "fall_pct": float(100 * (R_ex[0] - R_ex[-1]) / R_ex[0]),
                      "slope": b, "ci": [lo, hi]}
    print("  R exact: %.3f -> %.3f  fall %.1f%%  slope %+.4f HAC [%+.4f,%+.4f]"
          % (R_ex[0], R_ex[-1], ctl["R_exact"]["fall_pct"], b, lo, hi))

    rl_exact = relabel_pairs(U["exact"], years, NPERM_RL,
                             np.random.default_rng(SEED + 1))
    ctl["relabel_exact_above"] = sum(r["above"] for r in rl_exact)
    ctl["relabel_exact_pairs"] = len(rl_exact)
    print("  random-labelling infill, exact: %d of %d pairs ABOVE the envelope "
          "(%d inside, %d below)"
          % (ctl["relabel_exact_above"], len(rl_exact),
             sum(r["inside_note"] if False else 0 for r in rl_exact),
             sum(r["below"] for r in rl_exact)))
    print("  -> published value for this test is 12 of 13 above; the 2026 pair is "
          "one year longer here only if the roster changed.")
    res["control"] = ctl
    res["relabel_exact"] = rl_exact

    # ============================================================ 1. R + TRENDS
    print("\n" + "=" * 78)
    print("[1] CLARK-EVANS R AND ITS TREND, BY UNIT")
    print("=" * 78)
    blocks = {}
    for tag in TOLS:
        R = np.array([ce_r(U[tag][y], A_hull) for y in years])
        b, se, lo, hi = hac(np.array(years, float), R)
        rows = [{"year": y, "n": int(len(U[tag][y])), "R": float(R[i])}
                for i, y in enumerate(years)]
        blocks[tag] = {"rows": rows, "slope": b, "se": se, "ci": [lo, hi],
                       "fall_pct": float(100 * (R[0] - R[-1]) / R[0])}
        print("  %-8s n2026=%3d  R %.3f -> %.3f  fall %5.1f%%  slope %+.5f "
              "HAC [%+.5f,%+.5f]  %s"
              % (tag, len(U[tag][2026]), R[0], R[-1], blocks[tag]["fall_pct"],
                 b, lo, hi, "excludes 0" if lo * hi > 0 else "contains 0"))
    res["R"] = blocks

    # ====================================================== 2. MULTISCALE L + SHAPE
    print("\n" + "=" * 78)
    print("[2] MULTISCALE L, THE INHOMOGENEOUS NULL, AND THE SHAPE SERIES")
    print("=" * 78)
    step = BAND / 2.0
    gx = np.arange(poly[:, 0].min(), poly[:, 0].max() + step, step)
    gy = np.arange(poly[:, 1].min(), poly[:, 1].max() + step, step)
    GX, GY = np.meshgrid(gx, gy)
    C = np.column_stack([GX.ravel(), GY.ravel()])
    cen = poly.mean(axis=0)
    keep = np.ones(len(C), bool)
    for k in range(len(poly)):
        a, b2 = poly[k], poly[(k + 1) % len(poly)]
        e = b2 - a
        nrm = np.array([-e[1], e[0]])
        nrm = nrm / (np.linalg.norm(nrm) + 1e-12)
        if np.dot(cen - a, nrm) < 0:
            nrm = -nrm
        keep &= (C @ nrm) >= (float(np.dot(nrm, a)) - 1e-9)
    C = C[keep]
    print("  intensity grid: %d cells inside the hull at %d m spacing" % (len(C), step))

    lblocks = {}
    for tag in TOLS:
        rows, nulls = [], []
        for y in years:
            P = U[tag][y]
            L = L_border(P, A_hull, lines=lines)
            d = cKDTree(P).query(C, k=min(len(P), 100))[0]
            w = np.clip(np.exp(-0.5 * (d / BAND) ** 2).sum(axis=1), 1e-12, None)
            pr = w / w.sum()
            null = np.empty((NNULL, len(RS)))
            for j in range(NNULL):
                ix = rng.choice(len(C), len(P), replace=False, p=pr)
                Q = C[ix] + rng.normal(0, BAND / 4.0, (len(P), 2))
                null[j] = L_border(Q, A_hull, lines=lines)
            nulls.append(null)
            rows.append({"year": y, "n": int(len(P)),
                         "L": [None if not np.isfinite(v) else float(v) for v in L]})
        arr = np.array([[np.nan if v is None else v for v in r["L"]] for r in rows])
        nlo = np.array([np.nanpercentile(nn, 2.5, axis=0) for nn in nulls])
        nhi = np.array([np.nanpercentile(nn, 97.5, axis=0) for nn in nulls])
        nmed = np.array([np.nanpercentile(nn, 50, axis=0) for nn in nulls])
        counts = {}
        for i, r in enumerate(RS):
            above = int((arr[:, i] > nhi[:, i]).sum())
            below = int((arr[:, i] < nlo[:, i]).sum())
            counts[str(r)] = {"above": above, "within": 14 - above - below, "below": below}
        norm = {int(r["year"]): (np.array(r["L"]) / arr[len(rows) - 1, -1]).tolist()
                for r in rows}
        lblocks[tag] = {"rows": rows, "null_lo": nlo.tolist(), "null_hi": nhi.tolist(),
                        "null_med": nmed.tolist(), "vs_inhomogeneous": counts,
                        "normalised": {str(k): v for k, v in norm.items()}}
        i10 = int(np.where(RS == 1000)[0][0])
        s, se, lo, hi = hac(np.array(years, float), arr[:, i10])
        s2, _, _, _ = hac(np.array(years[1:], float), arr[1:, i10])
        s3, _, _, _ = hac(np.array(years[2:], float), arr[2:, i10])
        lblocks[tag]["l1km"] = {"all": s, "ci": [lo, hi], "no2013": s2, "no2013_14": s3}
        print("  %-8s 1km slope %+7.1f [%+7.1f,%+7.1f];  no2013 %+7.1f; no2013-14 %+7.1f"
              % (tag, s, lo, hi, s2, s3))
        print("           above inhomogeneous null: "
              + " ".join("%d/14" % counts[str(r)]["above"] for r in RS))
        print("           500m/2km shape 2020 %.3f 2026 %.3f"
              % (norm[2020][2], norm[2026][2]))
    res["L"] = lblocks

    # ============================================================== 3. INFILL TESTS
    print("\n" + "=" * 78)
    print("[3] INFILL: RANDOM-LABELLING AND NEW-TO-NEW, BY UNIT")
    print("=" * 78)
    rl_blocks, batch_blocks = {}, {}
    for tag in TOLS:
        rl = relabel_pairs(U[tag], years, NPERM_RL, np.random.default_rng(SEED + 2))
        ba = batch_pairs(U[tag], years, NPERM_BATCH, np.random.default_rng(SEED + 3))
        rl_blocks[tag] = {"rows": rl, "above": sum(r["above"] for r in rl),
                          "below": sum(r["below"] for r in rl), "pairs": len(rl)}
        batch_blocks[tag] = {"rows": ba, "clustered": sum(r["clustered"] for r in ba),
                             "pairs": len(ba)}
        # the infill count the paper reports: pairs whose new set is CLOSER than chance
        closer = sum(r["below"] for r in rl)
        print("  %-8s random-labelling: %2d/%2d ABOVE envelope (outward), %d closer "
              "than chance" % (tag, rl_blocks[tag]["above"], len(rl),
                               closer))
        print("           new-to-new clustered: %2d/%2d year pairs"
              % (batch_blocks[tag]["clustered"], len(ba)))
    res["relabel"] = rl_blocks
    res["batch"] = batch_blocks

    # ====================================================== 4. LEAVE-ONE-OUT, THEMES
    print("\n" + "=" * 78)
    print("[4] LEAVE-ONE-THEME-OUT AND THEME-STRATIFIED TRENDS, BY UNIT")
    print("=" * 78)

    def theme_of(tv: str) -> str:
        """Map a Theme/Variable cell to one of the paper's theme groups.

        The archive cell reads e.g. 'Air Quality/Air Quality Index'. The published
        analysis groups on the THEME, and the mapping has to be the same one for
        every unit, so it is stated here once rather than inferred per year.
        """
        t = (tv or "").strip().lower()
        theme = t.split("/")[0]
        groups = {
            "vehicles": "Vehicles", "vehicle": "Vehicles", "traffic": "Vehicles",
            "weather": "Weather",
            "air quality": "Air Quality", "air": "Air Quality",
            "people": "People", "pedestrian": "People",
            "water level": "Water Level", "water": "Water Level",
            "sensor metrics": "Sensor Metrics", "metrics": "Sensor Metrics",
        }
        for key, name in groups.items():
            if theme.startswith(key):
                return name
        return "Other"

    loo_blocks, theme_blocks = {}, {}
    for tag in TOLS:
        # the unit's 2026 members, with their theme labels aligned to the survivors
        P26, tv26 = [], []
        d26 = yrs[2026]
        raw26 = np.array([(v[0], v[1]) for v in d26.values()], float)
        tvs26 = np.array([v[2] for v in d26.values()])
        if tag == "exact":
            keep_idx = np.sort(np.unique(np.round(raw26, 1), axis=0,
                                         return_index=True)[1])
        else:
            keep_idx = np.sort(np.unique(labels_single(raw26, TOLS[tag]),
                                         return_index=True)[1])
        P26, tv26 = raw26[keep_idx], tvs26[keep_idx]
        base = ce_r(P26, A_hull)
        loo = {}
        for th in sorted(set(theme_of(t) for t in tv26)):
            sel = np.array([theme_of(t) != th for t in tv26])
            if sel.sum() >= 5:
                loo[th] = {"n": int(sel.sum()), "R": ce_r(P26[sel], A_hull)}
        loo_blocks[tag] = {"n_2026": int(len(P26)), "R_2026": base, "leave_one_out": loo}
        print("  %-8s 2026 n=%3d R=%.3f | " % (tag, len(P26), base)
              + "  ".join("%s %.3f (n=%d)" % (k, v["R"], v["n"])
                          for k, v in sorted(loo.items())))

        # theme-stratified trend, the same theme set on every unit so the rows compare
        allthemes = sorted(set(theme_of(t)
                               for y in years for t in
                               [v[2] for v in yrs[y].values()]))
        per_theme = {}
        for th in allthemes:
            ser = []
            for y in years:
                dd = yrs[y]
                # build the theme's own unit: merge within the theme
                pts = [(v[0], v[1]) for v in dd.values() if theme_of(v[2]) == th]
                if len(pts) < 5:
                    ser.append(np.nan)
                    continue
                Q = np.array(pts, float)
                if tag == "exact":
                    Q = np.unique(np.round(Q, 1), axis=0)
                else:
                    Q = reps_first(Q, labels_single(Q, TOLS[tag]))
                ser.append(ce_r(Q, A_hull))
            ser = np.array(ser, float)
            ok = np.isfinite(ser)
            if ok.sum() >= 5:
                s, se, lo, hi = hac(np.array(years, float)[ok], ser[ok])
                per_theme[th] = {"slope": s, "ci": [lo, hi], "n_years": int(ok.sum()),
                                 "first": float(ser[ok][0]), "last": float(ser[ok][-1])}
        theme_blocks[tag] = per_theme
        print("           theme slopes: " + "  ".join(
            "%s %+.4f" % (k, v["slope"]) for k, v in sorted(per_theme.items())))
    res["leave_one_out"] = loo_blocks
    res["theme_trends"] = theme_blocks

    # ================================================= 5. RAREFACTION, GINI, CHURN
    print("\n" + "=" * 78)
    print("[5] RAREFIED R, GINI, AND LOCATION-LEVEL CHURN, BY UNIT")
    print("=" * 78)
    rare_blocks, gini_blocks, churn_blocks = {}, {}, {}
    for tag in TOLS:
        ns = np.array([len(U[tag][y]) for y in years])
        nmin = int(ns.min())
        r = np.random.default_rng(SEED + 4)
        rare = np.array([
            float(np.mean([ce_r(U[tag][y][r.choice(len(U[tag][y]), nmin, replace=False)],
                                A_hull) for _ in range(NRAKE)]))
            for y in years])
        s, se, lo, hi = hac(np.array(years, float), rare)
        # fixed-hull rarefaction (the paper's version), not per-year box
        rare_blocks[tag] = {"nmin": nmin, "series": rare.tolist(), "slope": s,
                            "ci": [lo, hi],
                            "contains_zero": bool(lo * hi <= 0)}
        print("  %-8s rarefied R to n=%3d: %.3f -> %.3f  slope %+.5f "
              "[%+.5f,%+.5f]  %s"
              % (tag, nmin, rare[0], rare[-1], s, lo, hi,
                 "null" if lo * hi <= 0 else "NON-null"))

        # Gini on the paper's fixed grid: origin at the minimum coordinate of the
        # pooled record and a span covering all of it, so years are comparable.
        gi = []
        for y in years:
            gi.append(gini_fixed_grid(U[tag][y], GINI_ORG, GINI_CELL, GINI_NX))
        gi = np.array(gi, float)
        s2, se2, lo2, hi2 = hac(np.array(years, float), gi)
        rr = np.random.default_rng(SEED + 5)
        gir = np.array([
            float(np.mean([gini_fixed_grid(
                U[tag][y][rr.choice(len(U[tag][y]), nmin, replace=False)],
                GINI_ORG, GINI_CELL, GINI_NX) for _ in range(NRAKE)]))
            for y in years])
        s3, se3, lo3, hi3 = hac(np.array(years, float), gir)
        gini_blocks[tag] = {"raw_slope": s2, "raw_ci": [lo2, hi2],
                            "rare_slope": s3, "rare_ci": [lo3, hi3],
                            "raw_first": float(gi[0]), "raw_last": float(gi[-1])}
        print("  %-8s Gini raw %+.4f [%+.4f,%+.4f] | rarefied %+.4f [%+.4f,%+.4f]"
              % (tag, s2, lo2, hi2, s3, lo3, hi3))

        # location-level churn: identifiers present this year but not the previous
        pres = []
        for y in years:
            pres.append({tuple(p) for p in U[tag][y]})
        births, deaths = [], []
        for k in range(1, len(years)):
            births.append(len(pres[k] - pres[k - 1]))
            deaths.append(len(pres[k - 1] - pres[k]))
        churn_blocks[tag] = {"births": births, "deaths": deaths,
                             "birth_mean": float(np.mean(births)),
                             "death_mean": float(np.mean(deaths))}
        print("  %-8s churn per transition: births mean %.0f, deaths mean %.0f"
              % (tag, np.mean(births), np.mean(deaths)))
    res["rarefied_R"] = rare_blocks
    res["gini"] = gini_blocks
    res["churn"] = churn_blocks

    # ===================================================== 6. COORDINATE STABILITY
    print("\n" + "=" * 78)
    print("[6] COORDINATE STABILITY (report item 10)")
    print("=" * 78)
    seen, moved, n_coord_changes = {}, 0, 0
    for y in years:
        for k, v in yrs[y].items():
            p = (round(v[0], 6), round(v[1], 6))
            if k in seen and seen[k] != p:
                moved += 1
                n_coord_changes += 1
            seen[k] = p
    print("  %d identifiers appear in more than one year; %d have a coordinate that "
          "changes between the first and last appearance at 1e-6 deg rounding"
          % (len(seen), moved))
    # more precise: compare the full set of coordinates seen per identifier
    coords = {}
    for y in years:
        for k, v in yrs[y].items():
            coords.setdefault(k, set()).add((round(v[0], 7), round(v[1], 7)))
    multi = {k: v for k, v in coords.items() if len(v) > 1}
    print("  %d identifiers hold more than one distinct coordinate across the record "
          "(%.1f%% of %d)" % (len(multi), 100 * len(multi) / len(coords), len(coords)))
    offs = []
    for k, v in list(multi.items())[:500]:
        A = np.array(sorted(v))
        offs.append(float(np.linalg.norm(A.max(axis=0) - A.min(axis=0))))
    if offs:
        print("  for those, the spread of their own coordinates: median %.2f m, "
              "p95 %.2f m, max %.2f m"
              % (np.median(offs), np.percentile(offs, 95), max(offs)))
    res["coordinate_stability"] = {"identifiers": len(coords),
                                   "multi_coordinate": len(multi),
                                   "pct_multi": 100 * len(multi) / len(coords)}

    # =========================================================== 7. OUTLIER-ROBUST R
    print("\n" + "=" * 78)
    print("[7] OUTLIER-ROBUST R (report item 9)")
    print("=" * 78)
    rob = {}
    for tag in TOLS:
        med, tr = [], []
        for y in years:
            P = U[tag][y]
            nn = np.sort(cKDTree(P).query(P, k=2)[0][:, 1])
            rho = len(P) / A_hull
            # the CSR expectation of the SAME statistic, so the ratio is an index
            # that is 1 under randomness. Using the mean's expectation here would
            # compare a median against a mean and report the difference as a fall.
            e_med = math.log(2.0) / (math.pi * rho) ** 0.5
            k = max(1, int(0.1 * len(nn)))
            trimmed = nn[:-k]
            med.append(float(np.median(nn) / e_med))
            tr.append(float(trimmed.mean() / (1.0 / (2.0 * math.sqrt(rho)))))
        b1, _, lo1, hi1 = hac(np.array(years, float), np.array(med))
        b2, _, lo2, hi2 = hac(np.array(years, float), np.array(tr))
        rob[tag] = {"median": {"first": med[0], "last": med[-1], "slope": b1,
                               "ci": [lo1, hi1],
                               "fall_pct": 100 * (med[0] - med[-1]) / med[0]},
                    "trim10": {"first": tr[0], "last": tr[-1], "slope": b2,
                               "ci": [lo2, hi2],
                               "fall_pct": 100 * (tr[0] - tr[-1]) / tr[0]}}
        print("  %-8s mean-NN R fell %.1f%% | median-NN index %.3f -> %.3f, fell %.1f%% "
              "(%+.5f [%+.5f,%+.5f]) | trimmed-10%% index fell %.1f%% (%+.5f [%+.5f,%+.5f])"
              % (tag, blocks[tag]["fall_pct"],
                 med[0], med[-1], rob[tag]["median"]["fall_pct"], b1, lo1, hi1,
                 rob[tag]["trim10"]["fall_pct"], b2, lo2, hi2))
    res["robust_R"] = rob

    (HERE / "results_sites.json").write_text(json.dumps(res, indent=1))
    print("\nwrote results_sites.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
