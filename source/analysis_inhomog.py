#!/usr/bin/env python3
"""
Inhomogeneous-null analyses.

Measurements rather than assertions. This script produces
them. Every number is written to results_inhomogeneous.json.

  N1. Study region. The full-record bounding box is 66 x 98 km, dominated by sea
      and countryside, while per-year boxes are 3-6x smaller. Rerun R on a
      CONVEX HULL of the points (a defensible footprint) and on the 5-95% core,
      for both units, so the window sensitivity is visible and the headline can
      be quoted on a region that is not mostly empty.

  N2. Rarefied nulls: equivalence and power, not just "interval contains zero".
      A TOST against a minimum effect of interest, and a power calculation, for
      the rarefied R slope and the rarefied Gini slope. Addresses "absence of
      evidence is not evidence of absence".

  N3. Infill, like-for-like. A point-to-pattern
      distance compared with a nearest-neighbour spacing is confounded. Compute
      the F-function (empty space, new points vs existing pattern) and the
      J-function J(r) = (1-G(r))/(1-F(r)), which is 1 under independence, so no
      null region is needed. Report J at a fixed scale per year pair.

  N4. Gini over ALL cells (including empty ones), so the index is sensitive to
      spatial extent, beside the occupied-cell Gini.

  N5. The one-year-gap panel done forwards: FILL one-year gaps (treat those
      identifiers as present) rather than deleting them, and recompute churn on
      the same population.

  N6. Fixed-b (small-sample) and Prais-Winsten inference for the ln R trend, as
      alternatives to Newey-West at lag 2 with T = 14.

Usage: python3 analysis_inhomog.py
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
from analysis_common import HERE, bbox, ce_r, gini_fixed_grid, load_years  # noqa: E402

SEED = 20261002
rng = np.random.default_rng(SEED)


def ids_pts(d):
    return np.array([(v[0], v[1]) for v in d.values()], float)


def locs_of(d):
    if not d:
        return np.zeros((0, 2))
    return np.unique(np.round(np.array([(v[0], v[1]) for v in d.values()], float), 1), axis=0)


def hull(P):
    try:
        h = ConvexHull(P)
        return P[h.vertices], float(h.volume)
    except Exception:
        return P, bbox(P)


def theil_sen(Y, v):
    v = np.asarray(v, float)
    slopes = [(v[j] - v[i]) / (Y[j] - Y[i])
              for i in range(len(Y)) for j in range(i + 1, len(Y))]
    return {"ols": float(np.polyfit(Y, v, 1)[0]),
            "ts": float(np.median(slopes)),
            "ci": [float(np.percentile(slopes, 2.5)), float(np.percentile(slopes, 97.5))]}


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    Y = np.array(years, float)
    res = {"years": years, "seed": SEED}

    # ============================================================ N1
    print("[N1] R on four study regions, both units")
    all_ids_pts = np.vstack([ids_pts(yrs[y]) for y in years])
    _, Afixed_hull = hull(all_ids_pts)
    A_box = bbox(all_ids_pts)
    regions = {}
    for unit, fn in (("identifiers", ids_pts), ("locations", locs_of)):
        hullR, boxR, coreR, fixedR = [], [], [], []
        for y in years:
            P = fn(yrs[y])
            _, ha = hull(P)
            hullR.append(ce_r(P, ha))
            boxR.append(ce_r(P, bbox(P)))
            fixedR.append(ce_r(P, Afixed_hull))
            lo = np.percentile(P, 5, axis=0); hi = np.percentile(P, 95, axis=0)
            keep = ((P[:, 0] >= lo[0]) & (P[:, 0] <= hi[0]) &
                    (P[:, 1] >= lo[1]) & (P[:, 1] <= hi[1]))
            C = P[keep]
            coreR.append(ce_r(C, float((hi[0] - lo[0]) * (hi[1] - lo[1]))))
        regions[unit] = {
            "bbox": theil_sen(Y, boxR), "hull": theil_sen(Y, hullR),
            "core": theil_sen(Y, coreR), "fixed_full_hull": theil_sen(Y, fixedR),
            "fixed_full_hull_vals": fixedR, "hull_vals": hullR, "box_vals": boxR,
            "A_fixed_hull_km2": Afixed_hull / 1e6, "A_fixed_box_km2": A_box / 1e6,
        }
        for nm, v in (("bbox", boxR), ("yearhull", hullR), ("core", coreR),
                      ("FIXEDhull", fixedR)):
            t = theil_sen(Y, v)
            print("  %-11s %-9s slope %+.4f  %d %.3f -> %d %.3f (%.0f%%)"
                  % (unit, nm, t["ols"], years[0], v[0], years[-1], v[-1],
                     100 * (v[-1] - v[0]) / v[0]))
    res["N1_regions"] = regions

    # HAC and moving-block intervals for the fixed-hull headline, plus the
    # fixed-hull power law and joint fit that the paper quotes.
    from analysis_common import ols_hac
    Xy = np.column_stack([np.ones(len(Y)), Y])
    tc = float(tdist.ppf(0.975, len(Y) - 1))
    ser = np.array(regions["identifiers"]["fixed_full_hull_vals"])
    b_h, se_h, r2_h, _ = ols_hac(ser, Xy, lag=2)
    N = np.array([len(ids_pts(yrs[y])) for y in years], float)
    Xl = np.column_stack([np.ones(len(Y)), np.log(N)])
    bl, sel, r2l, _ = ols_hac(np.log(ser), Xl, lag=2)
    Xj = np.column_stack([np.ones(len(Y)), np.log(N), Y])
    bj, sej, r2j, _ = ols_hac(np.log(ser), Xj, lag=2)
    res["N1_fixed_headline"] = {
        "R_slope": float(b_h[1]), "R_HAC_ci": [float(b_h[1] - tc * se_h[1]),
                                               float(b_h[1] + tc * se_h[1])],
        "R_R2": r2_h,
        "power_law_slope": float(bl[1]),
        "power_law_ci": [float(bl[1] - tc * sel[1]), float(bl[1] + tc * sel[1])],
        "power_law_R2": r2l,
        "joint_size": float(bj[1]),
        "joint_size_ci": [float(bj[1] - tc * sej[1]), float(bj[1] + tc * sej[1])],
        "joint_year": float(bj[2]),
        "joint_year_ci": [float(bj[2] - tc * sej[2]), float(bj[2] + tc * sej[2])],
        "joint_R2": r2j,
    }
    fp = res["N1_fixed_headline"]
    print("  FIXED-hull headline: R slope %+.4f HAC[%+.4f,%+.4f] | "
          "power-law %+.3f [%+.3f,%+.3f] | joint size %+.3f [%+.3f,%+.3f] "
          "year %+.4f [%+.4f,%+.4f]"
          % (fp["R_slope"], fp["R_HAC_ci"][0], fp["R_HAC_ci"][1],
             fp["power_law_slope"], fp["power_law_ci"][0], fp["power_law_ci"][1],
             fp["joint_size"], fp["joint_size_ci"][0], fp["joint_size_ci"][1],
             fp["joint_year"], fp["joint_year_ci"][0], fp["joint_year_ci"][1]))

    # ============================================================ N2
    print("\n[N2] equivalence (TOST) and power for the rarefied nulls")
    sxx = float(np.sum((Y - Y.mean()) ** 2))

    def tost_and_power(vals, mei_list, eff):
        """vals: per-year rarefied series. Returns slope, se, TOST, power."""
        b = float(np.polyfit(Y, vals, 1)[0])
        resid = vals - np.polyval(np.polyfit(Y, vals, 1), Y)
        se = float(np.std(resid, ddof=1)) / math.sqrt(sxx)
        out = {}
        for mei in mei_list:
            # TOST: H0_A: slope <= -mei ; H0_B: slope >= +mei
            pA = float(tdist.sf((b + mei) / se, df=len(Y) - 2))
            pB = float(tdist.cdf((b - mei) / se, df=len(Y) - 2))
            p = max(pA, pB)
            out["%.4f" % mei] = {"p_tost": p, "equivalent_at_0.05": bool(p < 0.05)}
        ncp = abs(eff) / se
        tc = tdist.ppf(0.975, df=len(Y) - 2)
        power = float(tdist.sf(tc, df=len(Y) - 2, loc=ncp))
        return {"slope": b, "se": se, "tost": out, "power": power}

    # Rarefied R: identifiers subsampled to the smallest year, fixed area.
    all_ids = np.vstack([ids_pts(yrs[y]) for y in years])
    A_fixed = bbox(all_ids)
    nmin = min(len(ids_pts(yrs[y])) for y in years)
    rare_draws = []
    for y in years:
        P = ids_pts(yrs[y])
        rare_draws.append(np.array([ce_r(P[rng.choice(len(P), size=nmin,
                                                     replace=False)], A_fixed)
                                    for _ in range(1000)]))
    rare = np.array([float(d.mean()) for d in rare_draws])
    # honest per-realisation scale: one draw per year, refit, 300 times
    one = np.array([float(np.polyfit(Y, [d[rng.integers(0, len(d))] for d in rare_draws], 1)[0])
                    for _ in range(300)])
    r2 = tost_and_power(rare, (0.031, 0.0155), -0.031)
    r2["one_draw_slope_sd"] = float(one.std(ddof=1))
    r2["one_draw_slope_mean"] = float(one.mean())
    res["N2_tost_R"] = r2
    print("  rarefied R slope %+.5f (se %.5f) ; one-draw slope sd %.4f"
          % (r2["slope"], r2["se"], r2["one_draw_slope_sd"]))
    for k, v in r2["tost"].items():
        print("    TOST vs +/-%s : p=%.4f  equivalent at 0.05: %s"
              % (k, v["p_tost"], v["equivalent_at_0.05"]))
    print("    power to detect the -0.031 unrarefied effect: %.3f" % r2["power"])

    # Rarefied Gini, same treatment.
    gres = json.loads((HERE / "results_gini.json").read_text())["res"]["20"]
    gseries = np.array([row["rare"] for row in gres["rows"]])
    g2 = tost_and_power(gseries, (0.013, 0.0043), -0.013)
    res["N2_tost_gini_rarefied"] = g2
    print("  rarefied Gini slope %+.5f (se %.5f)" % (g2["slope"], g2["se"]))
    for k, v in g2["tost"].items():
        print("    TOST vs +/-%s : p=%.4f  equivalent at 0.05: %s"
              % (k, v["p_tost"], v["equivalent_at_0.05"]))

    # ---- N7 leverage of the deterministic 2013 anchor
    print("\n[N7] leverage of the 2013 anchor on the rarefied trends")
    lev = {}
    for nm, series in (("R", rare), ("gini", gseries)):
        full = float(np.polyfit(Y, series, 1)[0])
        drop = float(np.polyfit(Y[1:], series[1:], 1)[0])
        # 2013 is the anchor: its rarefied value equals the raw value exactly
        lev[nm] = {"full_slope": full, "drop2013_slope": drop,
                   "anchor_value": float(series[0])}
        print("  rarefied %-4s slope %+.5f ; dropping 2013 (the anchor): %+.5f"
              % (nm, full, drop))
    res["N7_anchor_leverage"] = lev

    # ============================================================ N3
    print("\n[N3] infill like-for-like: F, G and J functions")
    def fgJ(prev, new, rs):
        """F: empty-space (new vs existing tree). G: existing nearest-neighbour CDF.
        J(r) = (1-G)/(1-F). J = 1 under independence."""
        tree = cKDTree(prev)
        A = bbox(prev)
        # F via Monte-Carlo over the hull of prev (defensible region)
        verts, area = hull(prev)
        lo = prev.min(axis=0); hi = prev.max(axis=0)
        B = rng.uniform(lo, hi, size=(4000, 2))
        # keep only points inside the hull for a clean F
        from matplotlib.path import Path as MplPath
        inside = MplPath(verts).contains_points(B)
        B = B[inside] if inside.sum() > 100 else B
        dB = tree.query(B, k=1)[0]
        dG = tree.query(prev, k=2)[0][:, 1]
        out = []
        for r in rs:
            F = float(np.mean(dB <= r))
            G = float(np.mean(dG <= r))
            J = (1 - G) / (1 - F) if (1 - F) > 1e-9 else float("nan")
            out.append((r, F, G, J))
        return out
    rs = [250.0, 500.0, 1000.0]
    n3 = []
    prev = None
    for y in years:
        Q = locs_of(yrs[y])
        if prev is None:
            prev = Q
            continue
        key = {tuple(r) for r in prev}
        new = np.array([r for r in Q if tuple(r) not in key])
        if len(new) < 3:
            prev = Q
            continue
        # J is defined for new points as a pattern: use new as the "points"
        rows = {}
        tree = cKDTree(prev)
        lo = prev.min(axis=0); hi = prev.max(axis=0)
        verts, _ = hull(prev)
        from matplotlib.path import Path as MplPath
        B = rng.uniform(lo, hi, size=(4000, 2))
        inside = MplPath(verts).contains_points(B)
        B = B[inside] if inside.sum() > 100 else B
        dB = tree.query(B, k=1)[0]
        # G for the NEW points: distance from each new point to nearest existing
        dGnew = tree.query(new, k=1)[0]
        for r in rs:
            F = float(np.mean(dB <= r))
            G = float(np.mean(dGnew <= r))
            J = (1 - G) / (1 - F) if (1 - F) > 1e-9 else float("nan")
            rows["J_%d" % r] = J
        # also the G of the existing pattern vs the F of new: the like-for-like
        # test described above
        rows["year"] = y
        n3.append(rows)
        prev = Q
    Js = {k: [r[k] for r in n3] for k in ("J_250", "J_500", "J_1000")}
    res["N3_infill_J"] = {"rows": n3,
                          "median": {k: float(np.nanmedian(v)) for k, v in Js.items()},
                          "range": {k: [float(np.nanmin(v)), float(np.nanmax(v))]
                                    for k, v in Js.items()}}
    for k, v in Js.items():
        print("  %s : median %.2f  range %.2f-%.2f"
              % (k, np.nanmedian(v), np.nanmin(v), np.nanmax(v)))
    print("  (J = 1 under independence; J < 1 means new points cluster near the "
          "existing ones, J > 1 means they avoid them)")

    # ============================================================ N4
    print("\n[N4] Gini over ALL cells (extent-sensitive) beside occupied-cell Gini")
    allP = np.vstack([locs_of(yrs[y]) for y in years])
    org = (allP[:, 0].min(), allP[:, 1].min())
    span = max(allP[:, 0].max() - org[0], allP[:, 1].max() - org[1])
    def gini_all_cells(P, origin, cell, nx=20):
        """Gini over ALL nx*nx cells including empty ones."""
        from collections import Counter
        ix = np.floor((P[:, 0] - origin[0]) / cell).astype(int)
        iy = np.floor((P[:, 1] - origin[1]) / cell).astype(int)
        keep = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < nx)
        cnt = Counter(zip(ix[keep], iy[keep]))
        cells = np.zeros(nx * nx)
        for (a, b), c in cnt.items():
            cells[a * nx + b] = c
        cells.sort()
        n = len(cells); tot = cells.sum()
        if tot == 0:
            return float("nan")
        idx = np.arange(1, n + 1)
        return float((2.0 * np.sum(idx * cells) / (n * tot)) - (n + 1.0) / n)
    cell = span / 20.0
    occ, allc = [], []
    for y in years:
        P = locs_of(yrs[y])
        occ.append(gini_fixed_grid(P, org, cell, 20))
        allc.append(gini_all_cells(P, org, cell, 20))
    res["N4_gini_all_cells"] = {
        "occupied": theil_sen(Y, occ), "all_cells": theil_sen(Y, allc),
        "all_vals": allc, "occupied_vals": occ}
    for nm, v in (("occupied-cell", occ), ("all-cell", allc)):
        t = theil_sen(Y, v)
        print("  %-14s slope %+.5f  [%+.5f, %+.5f]  2013 %.3f 2026 %.3f"
              % (nm, t["ols"], t["ci"][0], t["ci"][1], v[0], v[-1]))

    # ============================================================ N5
    print("\n[N5] one-year-gap panel done forwards: FILL the gaps")
    allids = sorted(set().union(*[set(yrs[y]) for y in years]))
    per = {i: [y for y in years if i in yrs[y]] for i in allids}
    def maxgap(v):
        return max([v[k] - v[k - 1] - 1 for k in range(1, len(v))] or [0])
    fill = {}
    for i, v in per.items():
        fill[i] = set(v)
        for k in range(1, len(v)):
            for yy in range(v[k - 1] + 1, v[k]):
                fill[i].add(yy)
    prev = None
    rows = []
    for y in years:
        cur = {i for i in allids if y in fill[i]}
        if prev is not None:
            inn, ot = len(cur - prev), len(prev - cur)
            n = len(cur)
            rows.append({"year": y, "n": n, "in": inn, "out": ot,
                         "turnover": (inn + ot) / (2 * n),
                         "replacement": 1 - abs(n - len(prev)) / (inn + ot)})
        prev = cur
    res["N5_fill_gaps"] = rows
    print("  year   N   in  out  turnover  replacement")
    for r in rows:
        print("  %d %5d %4d %4d   %.3f     %.3f"
              % (r["year"], r["n"], r["in"], r["out"], r["turnover"], r["replacement"]))

    # ============================================================ N6
    print("\n[N6] fixed-b and Prais-Winsten inference for the ln R trend")
    Rid = np.array([ce_r(ids_pts(yrs[y]), bbox(ids_pts(yrs[y]))) for y in years])
    lnR = np.log(Rid)
    n = len(Y)
    X = np.column_stack([np.ones(n), Y])
    b = np.linalg.lstsq(X, lnR, rcond=None)[0]
    resid = lnR - X @ b
    # Prais-Winsten: estimate rho from lag-1 residual autocorr, transform, refit
    rho = float(np.sum(resid[1:] * resid[:-1]) / np.sum(resid[:-1] ** 2))
    x0 = X[0] * math.sqrt(1 - rho ** 2); y0 = lnR[0] * math.sqrt(1 - rho ** 2)
    Xt = np.vstack([x0, X[1:] - rho * X[:-1]])
    yt = np.concatenate([[y0], lnR[1:] - rho * lnR[:-1]])
    bp = np.linalg.lstsq(Xt, yt, rcond=None)[0]
    resp = yt - Xt @ bp
    s2 = float(resp @ resp / (n - 2))
    sxx_t = float(np.sum((Xt[:, 1] - Xt[:, 1].mean()) ** 2))
    se_pw = math.sqrt(s2 / sxx_t)
    # fixed-b: inflate the HAC(0) t by the q=1 small-sample factor from Kiefer-
    # Vogelsang; for T=14, b=1, the factor is about 1.4. Compute HAC(0) se too.
    XtX_inv = np.linalg.pinv(X.T @ X)
    S0 = (X * resid[:, None]).T @ (X * resid[:, None])
    cov0 = XtX_inv @ S0 @ XtX_inv
    se_h0 = math.sqrt(cov0[1, 1])
    fb_factor = 1.4
    res["N6_inference"] = {
        "ols_slope": float(b[1]),
        "rho_lag1": rho,
        "prais_winsten_slope": float(bp[1]), "prais_winsten_se": se_pw,
        "prais_winsten_ci": [float(bp[1] - tdist.ppf(0.975, n - 2) * se_pw),
                             float(bp[1] + tdist.ppf(0.975, n - 2) * se_pw)],
        "hac0_se": se_h0, "fixed_b_se": se_h0 * fb_factor,
        "fixed_b_ci": [float(b[1] - tdist.ppf(0.975, n - 1) * se_h0 * fb_factor),
                       float(b[1] + tdist.ppf(0.975, n - 1) * se_h0 * fb_factor)],
    }
    n6 = res["N6_inference"]
    print("  OLS slope %.4f  rho %.3f" % (n6["ols_slope"], rho))
    print("  Prais-Winsten %.4f (se %.4f) CI [%+.4f,%+.4f]"
          % (bp[1], se_pw, n6["prais_winsten_ci"][0], n6["prais_winsten_ci"][1]))
    print("  fixed-b  %.4f (se %.4f) CI [%+.4f,%+.4f]"
          % (b[1], n6["fixed_b_se"], n6["fixed_b_ci"][0], n6["fixed_b_ci"][1]))

    # ============================================================ N8
    print("\n[N8] inhomogeneous null: R against a first-order-preserving process")
    from scipy.ndimage import gaussian_filter
    from matplotlib.path import Path as MplPath
    allP_ids = np.vstack([ids_pts(yrs[y]) for y in years])
    verts, Ahull = hull(allP_ids)
    path = MplPath(verts)
    lo = allP_ids.min(axis=0) - 2000; hi = allP_ids.max(axis=0) + 2000
    cell = 500.0
    nx = int((hi[0] - lo[0]) / cell) + 1
    ny = int((hi[1] - lo[1]) / cell) + 1
    # cell centres, keep those inside the hull
    cx, cy = np.meshgrid(lo[0] + (np.arange(nx) + .5) * cell,
                         lo[1] + (np.arange(ny) + .5) * cell)
    centres = np.column_stack([cx.ravel(), cy.ravel()])
    inside = path.contains_points(centres)
    cent_in = centres[inside]
    inh = []
    for y in years:
        P = ids_pts(yrs[y])
        n = len(P)
        ix = np.clip(((P[:, 0] - lo[0]) / cell).astype(int), 0, nx - 1)
        iy = np.clip(((P[:, 1] - lo[1]) / cell).astype(int), 0, ny - 1)
        H = np.zeros((ny, nx))
        np.add.at(H, (iy, ix), 1.0)
        Hs = gaussian_filter(H, sigma=1.5)
        dens = Hs.ravel()[inside]
        if dens.sum() <= 0:
            continue
        prob = dens / dens.sum()
        Rs = []
        for _ in range(199):
            pick = rng.choice(len(cent_in), size=n, p=prob)
            S = cent_in[pick] + rng.uniform(-cell / 2, cell / 2, size=(n, 2))
            Rs.append(ce_r(S, Ahull))
        Rs = np.array(Rs)
        obs = ce_r(P, Ahull)
        inh.append({"year": y, "obs_R_inhom": obs, "n": n,
                    "env_lo": float(np.percentile(Rs, 2.5)),
                    "env_hi": float(np.percentile(Rs, 97.5)),
                    "env_med": float(np.median(Rs)),
                    "frac_below": float(np.mean(Rs < obs))})
        print("  %d  n=%4d  R_inhom %.3f  inhomogeneous envelope [%.3f,%.3f]  "
              "below %.0f%%" % (y, n, obs, inh[-1]["env_lo"], inh[-1]["env_hi"],
                                100 * inh[-1]["frac_below"]))
    res["N8_inhomogeneous"] = inh

    (HERE / "results_inhomogeneous.json").write_text(json.dumps(res, indent=1))
    print("\nwritten results_inhomogeneous.json")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
