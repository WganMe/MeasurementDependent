#!/usr/bin/env python3
"""
Annual membership-churn analysis.

Every quantity the round-five report asks to be measured rather than asserted, so
that no number in the manuscript is typed by hand.

  G. Rarefied Gini at an INTERMEDIATE sample size (150 and 200 distinct
     locations), for the years whose count allows it, with a trend test. The
     previous rarefaction used 39, the smallest year, which discards 93-95% of
     the later record and leaves an interval spanning roughly +-0.4 over the
     record.
  H. Rarefied Clark-Evans R: subsample every year's identifiers to a common N
     (the smallest non-degenerate year) and recompute R, so the contrast with the
     Gini is made on equal terms. R has never been rarefied.
  I. The post-2020 plateau, reported for BOTH series (identifiers and locations)
     with the seven values printed and a HAC slope / R^2 for each, so the text can
     name which series the slope refers to.
  J. The Equation 4 slope interval from the two methods that respect the ordering:
     Newey-West HAC (lag 2) and a circular moving-block bootstrap, replacing the
     independent bootstrap that the text itself says overstates precision.
  K. The replacement rate, and the demonstration that the turnover "excess" over
     the growth benchmark is the identity min(in,out)/N.
  L. The snapshot omission as a 2x2 table of vehicle share (omitted vs matched),
     with an odds ratio and a Fisher/chi-square p, in place of the binomial test
     whose base rate includes the omitted set. Plus coverage among still-active
     identifiers.
  M. Minor arithmetic the report corrects: the real N drop at 2018, and the growth
     factors for identifiers and locations.

Usage: python3 analysis_churn.py
Writes: results_churn.json
"""
from __future__ import annotations

import json
import math
import pathlib
import sqlite3
import sys

import numpy as np
from scipy.spatial import cKDTree
from scipy.stats import chi2_contingency, fisher_exact

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from analysis_common import (  # noqa: E402
    DB, HERE, bbox, ce_r, gini_fixed_grid, load_years, ols_hac,
)

SEED = 20261001
rng = np.random.default_rng(SEED)


def locs_of(d):
    if not d:
        return np.zeros((0, 2))
    return np.unique(np.round(np.array([(v[0], v[1]) for v in d.values()], float), 1), axis=0)


def ids_pts(d):
    return np.array([(v[0], v[1]) for v in d.values()], float)


def theil_sen(Y, v):
    v = np.asarray(v, float)
    slopes = [(v[j] - v[i]) / (Y[j] - Y[i])
              for i in range(len(Y)) for j in range(i + 1, len(Y))]
    return {"ols_slope": float(np.polyfit(Y, v, 1)[0]),
            "ts_slope": float(np.median(slopes)),
            "ts_ci": [float(np.percentile(slopes, 2.5)),
                      float(np.percentile(slopes, 97.5))]}


def circ_block_boot_ci(Y, v, block=3, n_boot=5000, rng=None):
    """Circular moving-block bootstrap CI for the OLS slope of v on Y."""
    rng = rng or np.random.default_rng(SEED)
    v = np.asarray(v, float)
    n = len(v)
    nb = int(math.ceil(n / block))
    out = []
    for _ in range(n_boot):
        starts = rng.integers(0, n, size=nb)
        idx = np.concatenate([(np.arange(s, s + block) % n) for s in starts])[:n]
        b = np.polyfit(Y[idx], v[idx], 1)[0]
        out.append(b)
    out = np.array(out)
    return [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))]


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    Y = np.array(years, float)
    res: dict = {"years": years, "seed": SEED}
    Nloc = np.array([len(locs_of(yrs[y])) for y in years])
    Nid = np.array([len(ids_pts(yrs[y])) for y in years])
    print("locations per year:", dict(zip(years, Nloc.tolist())))

    allP = np.vstack([locs_of(yrs[y]) for y in years])
    org = (allP[:, 0].min(), allP[:, 1].min())
    span = max(allP[:, 0].max() - org[0], allP[:, 1].max() - org[1])
    cell20 = span / 20.0

    # ============================================================ G
    print("\n[G] rarefied Gini at intermediate N (locations, 20x20 fixed grid)")
    G = {}
    for nmin in (39, 150, 200):
        rows = []
        for y in years:
            P = locs_of(yrs[y])
            if len(P) < nmin:
                rows.append({"year": y, "n": int(len(P)), "mean": None, "ci": None})
                continue
            vals = []
            for _ in range(1000):
                sub = P[rng.choice(len(P), size=nmin, replace=False)]
                g = gini_fixed_grid(sub, org, cell20, 20)
                if np.isfinite(g):
                    vals.append(g)
            rows.append({"year": y, "n": int(len(P)), "mean": float(np.mean(vals)),
                         "ci": [float(np.percentile(vals, 2.5)),
                                float(np.percentile(vals, 97.5))]})
        usable = [r for r in rows if r["mean"] is not None]
        Yg = np.array([r["year"] for r in usable], float)
        vv = np.array([r["mean"] for r in usable], float)
        tr = theil_sen(Yg, vv)
        tr["n_years"] = len(usable)
        tr["first_year"], tr["last_year"] = int(Yg[0]), int(Yg[-1])
        tr["span_over_record"] = float(tr["ols_slope"] * (years[-1] - years[0]))
        G[str(nmin)] = {"rows": rows, "trend": tr}
        ci = tr["ts_ci"]
        print("  N=%3d  %d years (%d-%d)  slope %+.4f  TS %+.4f [%+.4f, %+.4f]  span over record %.2f"
              % (nmin, len(usable), Yg[0], Yg[-1], tr["ols_slope"], tr["ts_slope"],
                 ci[0], ci[1], tr["span_over_record"]))
        if nmin in (150, 200):
            for r in usable:
                print("      %d  n=%-4d rare %.3f [%.3f,%.3f]"
                      % (r["year"], r["n"], r["mean"], r["ci"][0], r["ci"][1]))
    res["G_rarefied_gini"] = G

    # ============================================================ H
    print("\n[H] rarefied Clark-Evans R (identifiers, common N)")
    # smallest year with enough points to define R is 2013 (41 identifiers).
    NMIN_R = int(Nid.min())
    print("  common N = %d (year %d)" % (NMIN_R, years[int(np.argmin(Nid))]))
    H_rows = []
    for y in years:
        P = ids_pts(yrs[y])
        vals = []
        for _ in range(1000):
            sub = P[rng.choice(len(P), size=min(NMIN_R, len(P)), replace=False)]
            r = ce_r(sub, bbox(sub))
            if np.isfinite(r):
                vals.append(r)
        H_rows.append({"year": y, "n": int(len(P)), "R": float(np.mean(vals)),
                       "ci": [float(np.percentile(vals, 2.5)),
                              float(np.percentile(vals, 97.5))],
                       "R_raw": float(ce_r(P, bbox(P)))})
    vr = np.array([r["R"] for r in H_rows])
    raw_ids = np.array([r["R_raw"] for r in H_rows])
    tr = theil_sen(Y, vr)
    tr["slope"] = float(np.polyfit(Y, vr, 1)[0])
    res["H_rarefied_R"] = {
        "common_N": NMIN_R, "rows": H_rows, "trend": tr,
        "raw_identifier_slope": float(np.polyfit(Y, raw_ids, 1)[0]),
        "raw_identifier_first": float(raw_ids[0]),
        "raw_identifier_last": float(raw_ids[-1]),
    }
    print("  rarefied R (own bbox): %d %.3f -> %d %.3f  slope %+.4f TS %+.4f [%+.4f, %+.4f]"
          % (years[0], vr[0], years[-1], vr[-1], tr["ols_slope"], tr["ts_slope"],
             tr["ts_ci"][0], tr["ts_ci"][1]))
    print("  raw identifier R slope for comparison: %+.4f" % res["H_rarefied_R"]["raw_identifier_slope"])
    for r in H_rows:
        print("      %d  rare %.3f [%.3f,%.3f]  raw %.3f"
              % (r["year"], r["R"], r["ci"][0], r["ci"][1], r["R_raw"]))

    # H2: rarefy to a common N but hold the REFERENCE AREA fixed, so the test
    # isolates the arrangement and not the footprint. The area is the full-record
    # bounding box of all identifiers, used for every year and every subsample.
    all_ids_pts = np.vstack([ids_pts(yrs[y]) for y in years])
    A_fixed = bbox(all_ids_pts)
    print("  fixed reference area = %.1f km2" % (A_fixed / 1e6))
    H2 = {}
    for nmin in (NMIN_R, 150, 200):
        rows = []
        for y in years:
            P = ids_pts(yrs[y])
            if len(P) < nmin:
                rows.append({"year": y, "n": int(len(P)), "mean": None})
                continue
            vals = []
            for _ in range(1000):
                sub = P[rng.choice(len(P), size=nmin, replace=False)]
                r = ce_r(sub, A_fixed)
                if np.isfinite(r):
                    vals.append(r)
            rows.append({"year": y, "n": int(len(P)), "mean": float(np.mean(vals)),
                         "ci": [float(np.percentile(vals, 2.5)),
                                float(np.percentile(vals, 97.5))]})
        usable = [r for r in rows if r["mean"] is not None]
        Yh = np.array([r["year"] for r in usable], float)
        vv = np.array([r["mean"] for r in usable], float)
        t2 = theil_sen(Yh, vv)
        t2["n_years"] = len(usable)
        H2[str(nmin)] = {"rows": rows, "trend": t2}
        print("  fixed-area rarefied R at N=%3d: %d years  slope %+.4f TS %+.4f [%+.4f, %+.4f]"
              % (nmin, len(usable), t2["ols_slope"], t2["ts_slope"],
                 t2["ts_ci"][0], t2["ts_ci"][1]))
    res["H2_rarefied_R_fixed_area"] = {"A_fixed_km2": A_fixed / 1e6, "by_N": H2}

    # ============================================================ I
    print("\n[I] post-2020 plateau, both series, all seven values")
    Rloc = np.array([ce_r(locs_of(yrs[y]), bbox(locs_of(yrs[y]))) for y in years])
    Rid = np.array([ce_r(ids_pts(yrs[y]), bbox(ids_pts(yrs[y]))) for y in years])
    post = Y >= 2020
    plateau = {}
    for name, v in (("identifiers", Rid), ("locations", Rloc)):
        X = np.column_stack([np.ones(post.sum()), Y[post]])
        b, se, r2, _ = ols_hac(v[post], X, 2)
        plateau[name] = {
            "values": {int(y): float(x) for y, x in zip(Y[post], v[post])},
            "slope_hac": float(b[1]), "se": float(se[1]), "r2": float(r2),
            "ci": [float(b[1] - 1.96 * se[1]), float(b[1] + 1.96 * se[1])],
        }
        print("  %-12s values %s" % (name, ["%.3f" % x for x in v[post]]))
        print("               slope %+.4f (HAC se %.4f) R2 %.3f CI [%+.4f, %+.4f]"
              % (b[1], se[1], r2, plateau[name]["ci"][0], plateau[name]["ci"][1]))
    res["I_plateau"] = plateau

    # ============================================================ J
    print("\n[J] Equation 4 slope interval, HAC and block bootstrap")
    lnR = np.log(Rid)
    lnN = np.log(Nid)
    X = np.column_stack([np.ones_like(lnN), lnN])
    b, se, r2, _ = ols_hac(lnR, X, 2)
    j = {
        "slope": float(b[1]), "hac_se": float(se[1]),
        "hac_ci": [float(b[1] - 1.96 * se[1]), float(b[1] + 1.96 * se[1])],
        "block_boot_ci": circ_block_boot_ci(Y, lnR - (b[0] + b[1] * lnN), block=3),
        "r2": float(r2),
    }
    # block bootstrap directly on the fitted slope: resample (lnN, lnR) pairs in blocks
    boots = []
    n = len(Y); blk = 3; nb = int(math.ceil(n / blk))
    for _ in range(5000):
        starts = rng.integers(0, n, size=nb)
        ii = np.concatenate([(np.arange(s, s + blk) % n) for s in starts])[:n]
        bb = np.polyfit(lnN[ii], lnR[ii], 1)[0]
        boots.append(bb)
    boots = np.array(boots)
    j["block_boot_slope_ci"] = [float(np.percentile(boots, 2.5)),
                               float(np.percentile(boots, 97.5))]
    # the independent (iid) bootstrap the text says overstates precision, for contrast
    ib = []
    for _ in range(5000):
        ii = rng.integers(0, n, size=n)
        ib.append(np.polyfit(lnN[ii], lnR[ii], 1)[0])
    ib = np.array(ib)
    j["iid_boot_ci"] = [float(np.percentile(ib, 2.5)), float(np.percentile(ib, 97.5))]
    res["J_powerlaw_ci"] = j
    print("  slope %.4f  HAC [%+.3f, %+.3f]  block-boot [%+.3f, %+.3f]  iid-boot [%+.3f, %+.3f]  R2 %.3f"
          % (j["slope"], j["hac_ci"][0], j["hac_ci"][1],
             j["block_boot_slope_ci"][0], j["block_boot_slope_ci"][1],
             j["iid_boot_ci"][0], j["iid_boot_ci"][1], j["r2"]))

    # ============================================================ K
    print("\n[K] replacement rate, and the identity excess = min(in,out)/N")
    prev = None
    K_rows = []
    for y in years:
        cur = set(yrs[y])
        if prev is not None:
            inn, ot = len(cur - prev), len(prev - cur)
            n = len(cur)
            repl = 1.0 - abs(n - len(prev)) / (inn + ot) if (inn + ot) else 0.0
            identity = min(inn, ot) / n
            K_rows.append({"year": y, "in": inn, "out": ot,
                           "replacement_rate": repl, "min_over_N": identity})
        prev = cur
    rr = np.array([r["replacement_rate"] for r in K_rows])
    res["K_replacement"] = {"rows": K_rows,
                            "median": float(np.median(rr)),
                            "min": float(rr.min()), "max": float(rr.max())}
    for r in K_rows:
        print("  %d in=%-4d out=%-4d  replacement %.3f  min/N %.3f (identity)"
              % (r["year"], r["in"], r["out"], r["replacement_rate"], r["min_over_N"]))
    print("  median replacement %.3f  range %.3f-%.3f" % (np.median(rr), rr.min(), rr.max()))

    # ============================================================ L
    print("\n[L] snapshot vehicle share, 2x2, and active coverage")
    con = sqlite3.connect(DB)
    snap = {str(r[0]).strip() for r in con.execute("SELECT raw_id FROM sensors") if r[0]}
    con.close()
    arch = {i for y in years for i in yrs[y]}

    def theme_class(i):
        for y in years:
            if i in yrs[y]:
                return yrs[y][i][2].split("/")[0]
        return "?"

    matched = snap & arch
    omitted = arch - snap
    veh_m = sum(1 for i in matched if theme_class(i) == "Vehicles")
    veh_o = sum(1 for i in omitted if theme_class(i) == "Vehicles")
    tab = np.array([[veh_m, len(matched) - veh_m],
                    [veh_o, len(omitted) - veh_o]])
    odds, p_fis = fisher_exact(tab)
    chi2, p_chi, _, _ = chi2_contingency(tab, correction=False)
    # still-active subset (present in any of 2024-2026)
    active = {i for i in arch if any(i in yrs[y] for y in (2024, 2025, 2026))}
    act_m = len(active & snap)
    res["L_snapshot_2x2"] = {
        "matched": len(matched), "omitted": len(omitted),
        "veh_matched": veh_m, "veh_omitted": veh_o,
        "pct_veh_matched": 100.0 * veh_m / len(matched),
        "pct_veh_omitted": 100.0 * veh_o / len(omitted),
        "odds_ratio": float(odds), "fisher_p": float(p_fis),
        "chi2": float(chi2), "chi2_p": float(p_chi),
        "active_total": len(active), "active_matched": act_m,
        "active_coverage_pct": 100.0 * act_m / len(active),
        "overall_coverage_pct": 100.0 * len(matched) / len(arch),
    }
    L = res["L_snapshot_2x2"]
    print("  matched veh %.1f%% (%d/%d)  omitted veh %.1f%% (%d/%d)"
          % (L["pct_veh_matched"], veh_m, len(matched),
             L["pct_veh_omitted"], veh_o, len(omitted)))
    print("  odds ratio %.2f  Fisher p %.3g  chi2 p %.3g"
          % (L["odds_ratio"], L["fisher_p"], L["chi2_p"]))
    print("  active (2024-2026) %d, matched %d -> coverage %.1f%% (overall %.1f%%)"
          % (L["active_total"], act_m, L["active_coverage_pct"], L["overall_coverage_pct"]))

    # ============================================================ K2
    print("\n[K2] infill, distance-to-existing vs existing nearest-neighbour spacing")
    # The alternative to ratio-to-a-null: compare the distance from a
    # newly appearing location to its nearest existing location, against (a) the
    # nearest-neighbour spacing among existing locations and (b) the same distance
    # for a RANDOM SUBSET of existing locations. Both are read off the same pattern,
    # so neither depends on drawing a null region.
    def locs_of_year(y):
        return locs_of(yrs[y])

    K2 = []
    prev = None
    for y in years:
        Q = locs_of_year(y)
        if prev is None:
            prev = Q
            continue
        key = {tuple(r) for r in prev}
        new = np.array([r for r in Q if tuple(r) not in key])
        if len(new) < 3 or len(prev) < 6:
            prev = Q
            continue
        tree = cKDTree(prev)
        d_new, _ = tree.query(new, k=1)
        # nearest-neighbour spacing among the existing locations (exclude self)
        nn_prev = tree.query(prev, k=2)[0][:, 1]
        # random subset of existing locations of the same size as the new set;
        # its nearest-OTHER-existing distance is read with k=2 to exclude self
        sub = prev[rng.choice(len(prev), size=min(len(new), len(prev)), replace=False)]
        d_sub = tree.query(sub, k=2)[0][:, 1]
        # fraction of new locations within the median existing spacing of an existing one
        med_spacing = float(np.median(nn_prev))
        K2.append({
            "year": y, "n_new": int(len(new)),
            "median_new_to_prev_m": float(np.median(d_new)),
            "median_existing_nn_m": float(med_spacing),
            "median_random_subset_m": float(np.median(d_sub)),
            "ratio_to_existing_nn": float(np.median(d_new) / med_spacing),
            "ratio_to_random_subset": float(np.median(d_new) / np.median(d_sub)),
            "frac_new_within_median_spacing": float(np.mean(d_new <= med_spacing)),
        })
        prev = Q
    res["K2_infill"] = K2
    r1 = np.array([r["ratio_to_existing_nn"] for r in K2])
    r2 = np.array([r["ratio_to_random_subset"] for r in K2])
    print("  ratio to existing NN spacing : %.2f-%.2f (median %.2f)"
          % (r1.min(), r1.max(), np.median(r1)))
    print("  ratio to random subset       : %.2f-%.2f (median %.2f)"
          % (r2.min(), r2.max(), np.median(r2)))

    # ============================================================ M
    print("\n[M] arithmetic check on 2018 and growth factors")
    i17, i18 = years.index(2017), years.index(2018)
    m = {
        "N_2017": int(Nid[i17]), "N_2018": int(Nid[i18]),
        "pct_drop_N": 100.0 * (Nid[i18] - Nid[i17]) / Nid[i17],
        "growth_identifiers": float(Nid[-1] / Nid[0]),
        "growth_locations": float(Nloc[-1] / Nloc[0]),
        "ids_first": int(Nid[0]), "ids_last": int(Nid[-1]),
        "locs_first": int(Nloc[0]), "locs_last": int(Nloc[-1]),
    }
    res["M_arithmetic"] = m
    print("  N 2017=%d -> 2018=%d = %+.1f%%" % (m["N_2017"], m["N_2018"], m["pct_drop_N"]))
    print("  growth: identifiers %.1fx (%d->%d), locations %.1fx (%d->%d)"
          % (m["growth_identifiers"], m["ids_first"], m["ids_last"],
             m["growth_locations"], m["locs_first"], m["locs_last"]))

    (HERE / "results_churn.json").write_text(json.dumps(res, indent=1))
    print("\nwritten results_churn.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
