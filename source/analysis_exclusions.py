#!/usr/bin/env python3
"""Round 15b: the remaining board-review gaps.

[3] The 24 snapshot identifiers that carry readings -- are they representative?
[4] The 179 snapshot-only identifiers -- themes and spatial spread.
[5] Minimum detectable effect for the rarefied concentration index, the analogue of
    the clustering MDE the paper already reports.
[6] Multiscale and infill sensitivity to excluding 2017-2018 and 2026, which the
    paper does for R only.

Writes: results_exclusions.json
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sqlite3
import sys

import numpy as np
from scipy.spatial import cKDTree
from scipy import stats

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from analysis_common import load_years, ols_hac                        # noqa: E402
from analysis_multiscale import (L_border, hull_edges,             # noqa: E402
                                      inward_lines, ids_of, locs_of, RS)

HERE = pathlib.Path(__file__).resolve().parent
# Committed benchmark snapshot (1,411 sensors; 2026-05-11 .. 2026-05-18).
# Override with UO_DB to use another copy.
DB = pathlib.Path(os.environ.get("UO_DB") or (HERE / "urban_observatory.db"))


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    Y = np.array(years, float)
    allP = np.vstack([ids_of(yrs[y]) for y in years])
    poly, A = hull_edges(allP)
    lines = inward_lines(poly)
    rng = np.random.default_rng(20261003)
    res = {"years": years}

    con = sqlite3.connect(DB)
    cur = con.cursor()
    snap = {str(r[0]).strip() for r in cur.execute("SELECT raw_id FROM sensors")}
    withread = {str(r[0]).strip() for r in
                cur.execute("SELECT DISTINCT sensor_name FROM readings")}
    con.close()
    census = set().union(*[set(yrs[y]) for y in years])

    def theme_of(i):
        for y in years:
            if i in yrs[y]:
                return str(yrs[y][i][2]).split("/")[0]
        return None

    # ------------------------------------------------------------------ [3]
    print("\n[3] the 24 reading-bearing snapshot identifiers")
    wr = sorted(withread)
    print("    in the snapshot  : %d of %d carry readings" % (len(wr), len(snap)))
    in_census = [i for i in wr if i in census]
    only_snap = [i for i in wr if i not in census]
    print("    of those, %d are in the census, %d appear only in the snapshot"
          % (len(in_census), len(only_snap)))
    themes = {}
    for i in in_census:
        themes.setdefault(theme_of(i), []).append(i)
    print("    theme mix of the reading-bearing identifiers:")
    allthemes = {}
    for i in census:
        allthemes.setdefault(theme_of(i), 0)
        allthemes[theme_of(i)] += 1
    tot_wr = len(in_census)
    for t, v in sorted(themes.items(), key=lambda kv: -len(kv[1])):
        print("      %-16s %2d (%.0f%% of reading-bearing, %.0f%% of the census)"
              % (t, len(v), 100 * len(v) / max(tot_wr, 1),
                 100 * allthemes.get(t, 0) / len(census)))
    res["reading_bearing"] = {
        "n": len(wr), "n_in_census": len(in_census), "n_snapshot_only": len(only_snap),
        "themes": {t: len(v) for t, v in themes.items()},
    }

    # ------------------------------------------------------------------ [4]
    print("\n[4] the 179 snapshot-only identifiers")
    only = sorted(snap - census)
    print("    count %d" % len(only))
    # are they spatially inside the network's footprint?
    pts = []
    for i in only:
        row = None
        con = sqlite3.connect(DB)
        con.row_factory = sqlite3.Row
        r = con.execute("SELECT centroid_lon, centroid_lat FROM sensors WHERE raw_id = ?",
                        (i,)).fetchone()
        con.close()
        if r and r["centroid_lon"] is not None:
            pts.append((float(r["centroid_lon"]), float(r["centroid_lat"])))
    print("    with usable coordinates: %d of %d" % (len(pts), len(only)))
    if pts:
        from analysis_common import proj
        P = np.array([proj(a, b) for a, b in pts])
        ok = np.ones(len(P), bool)
        for nrm, c in lines:
            ok &= (P @ nrm) >= (c - 1e-9)
        print("    inside the full-record hull      : %d of %d (%.0f%%)"
              % (ok.sum(), len(P), 100 * ok.mean()))
        # distance to the nearest census point
        C = np.vstack([locs_of(yrs[y]) for y in years])
        d = cKDTree(C).query(P, k=1)[0]
        print("    median distance to nearest census location: %.0f m (median census spacing %.0f m)"
              % (np.median(d), np.median(cKDTree(C).query(C, k=2)[0][:, 1])))
        res["snapshot_only"] = {"n": len(only), "n_with_coords": len(P),
                                "frac_inside_hull": float(ok.mean()),
                                "median_dist_to_census_m": float(np.median(d))}

    # ------------------------------------------------------------------ [5]
    print("\n[5] minimum detectable effect for the rarefied concentration index")
    g = json.loads((HERE / "results_gini.json").read_text())
    rare = np.array([r["rare"] for r in g["res"]["20"]["rows"]])
    X = np.column_stack([np.ones(14), Y])
    beta, se, r2, resid = ols_hac(rare, X, 2)
    so = math.sqrt((resid ** 2).sum() / 12 / ((Y - Y.mean()) ** 2).sum())
    tc80 = stats.t.ppf(0.90, 12) + stats.t.ppf(0.80, 12)   # two-sided 5%, 80% power
    mde80 = tc80 * so
    mde90 = (stats.t.ppf(0.90, 12) + stats.t.ppf(0.90, 12)) * so
    print("    OLS se of the rarefied Gini slope: %.5f" % so)
    print("    MDE at 80%% power: %.5f per year (%.1f%% of the uncorrected rise of 0.013)"
          % (mde80, 100 * mde80 / 0.0128))
    print("    MDE at 90%% power: %.5f" % mde90)
    res["gini_mde"] = {"se": float(so), "mde80": float(mde80), "mde90": float(mde90),
                       "uncorrected_slope": 0.0128}

    # ------------------------------------------------------------------ [6]
    print("\n[6] multiscale and infill with 2017-2018 and 2026 excluded")
    keep = np.array([y not in (2017, 2018, 2026) for y in years])
    Lk = []
    for y in years:
        P = locs_of(yrs[y])
        Lk.append(L_border(P, A, lines=lines))
    Lk = np.array([[np.nan if not np.isfinite(v) else v for v in row] for row in Lk])
    i5 = list(RS).index(500.0); i10 = list(RS).index(1000.0)
    for i, nm in ((i5, "500 m"), (i10, "1000 m")):
        col = Lk[:, i]
        sl_all = float(np.polyfit(Y, col, 1)[0])
        sl_sub = float(np.polyfit(Y[keep], col[keep], 1)[0])
        print("    L at %-7s slope: all years %+.1f m/yr, excluding 2017-18 and 2026 %+.1f m/yr"
              % (nm, sl_all, sl_sub))
    # does every year still clear the CSR envelope when the two are excluded?
    print("    (the envelope test is per year, so excluding years cannot change it)")
    res["multiscale_exclusions"] = {
        "slope_all_500": float(np.polyfit(Y, Lk[:, i5], 1)[0]),
        "slope_excl_500": float(np.polyfit(Y[keep], Lk[keep, i5], 1)[0]),
        "slope_all_1000": float(np.polyfit(Y, Lk[:, i10], 1)[0]),
        "slope_excl_1000": float(np.polyfit(Y[keep], Lk[keep, i10], 1)[0]),
    }

    inf = []
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
        pooled = np.vstack([prev, new])
        labels = np.array([0] * len(prev) + [1] * len(new))
        obs = float(np.median(cKDTree(prev).query(new, k=1)[0]))
        sims = np.array([float(np.median(cKDTree(pooled[l == 0]).query(pooled[l == 1], k=1)[0]))
                         for l in (labels[rng.permutation(len(pooled))]
                                   for _ in range(199))])
        inf.append({"year": y, "obs": obs, "hi": float(np.percentile(sims, 97.5)),
                    "lo": float(np.percentile(sims, 2.5))})
        prev = Q
    n_above = sum(1 for r in inf if r["obs"] > r["hi"])
    n_above_sub = sum(1 for r in inf if r["obs"] > r["hi"] and r["year"] not in (2017, 2018, 2026))
    n_sub = sum(1 for r in inf if r["year"] not in (2017, 2018, 2026))
    print("    infill: above the envelope in %d of %d pairs overall, %d of %d excluding those years"
          % (n_above, len(inf), n_above_sub, n_sub))
    res["infill_exclusions"] = {"n_above": n_above, "n": len(inf),
                                "n_above_sub": n_above_sub, "n_sub": n_sub}

    json.dump(res, open(HERE / "results_exclusions.json", "w"), indent=1)
    print("\nwrote results_exclusions.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
