#!/usr/bin/env python3
"""Independent cross-check of the multiscale estimator against spatstat.

The manuscript said in three places that spatstat's Lest had not been run because no
R interpreter was available. That gap is now closed: R 4.6.1 and spatstat.explore
3.8.3 are installed, crosscheck_spatstat.R exports spatstat's border-corrected L, and
this script compares it with the manuscript's own estimator on the same points and the
same window.

Convention note, which is a trap: the manuscript's L_border returns sqrt(K/pi) - r,
which is exactly spatstat's `border` column of Lest. Comparing the manuscript's value
against sqrt(K/pi) instead makes the two look 5-20% apart purely because of the -r.
That mistake was made once while building this check; it is recorded here so the
comparison cannot silently be done the wrong way again.

Usage:  python3 crosscheck_spatstat.py     (run crosscheck_spatstat.R first)
Writes: results_crosscheck.json
"""
from __future__ import annotations

import csv
import json
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from analysis_common import load_years  # noqa: E402
from analysis_multiscale import (  # noqa: E402
    locs_of, hull_edges, inward_lines, L_border,
)

SPATSTAT = pathlib.Path("/tmp/si_crosscheck/spatstat_L.csv")
RS = [100, 250, 500, 750, 1000, 1500, 2000]


def main() -> int:
    if not SPATSTAT.exists():
        print("run crosscheck_spatstat.R first (it writes %s)" % SPATSTAT)
        return 1

    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    allP = np.vstack([locs_of(yrs[y]) for y in years])
    poly, A = hull_edges(allP)
    lines = inward_lines(poly)

    sp: dict = {}
    for r in csv.DictReader(open(SPATSTAT)):
        sp.setdefault(int(r["year"]), {})[float(r["r"])] = float(r["spatstat_L"])

    res: dict = {"rs": RS, "per_scale": {}, "rows": []}
    by_scale: dict = {}
    for y in years:
        P = locs_of(yrs[y])
        ours = L_border(P, A, lines=lines, rs=RS)
        for i, r in enumerate(RS):
            # spatstat Lest `border` is L(r) - r; ours is the same quantity.
            theirs = sp[y][float(r)] - r
            pct = 100.0 * (ours[i] - theirs) / theirs if theirs else float("nan")
            res["rows"].append({"year": y, "r": r, "ours": float(ours[i]),
                                "spatstat": float(theirs), "pct_diff": float(pct)})
            by_scale.setdefault(r, []).append(abs(pct))

    print("manuscript estimator vs spatstat Lest (border correction)")
    print("  %-10s %12s %12s" % ("scale", "median |diff|", "max |diff|"))
    worst = 0.0
    for r in RS:
        med = float(np.median(by_scale[r]))
        mx = float(max(by_scale[r]))
        worst = max(worst, mx)
        res["per_scale"][str(r)] = {"median_pct": med, "max_pct": mx}
        print("  %6d m   %11.3f%% %11.3f%%" % (r, med, mx))
    res["worst_pct"] = worst
    res["verdict"] = ("agrees" if worst < 10.0 else "disagrees")

    # the headline value
    for row in res["rows"]:
        if row["year"] == 2026 and row["r"] == 1000:
            print("\n  L(1 km), 2026: ours %.1f m  spatstat %.1f m  (%.2f%% apart)"
                  % (row["ours"], row["spatstat"], row["pct_diff"]))
    print("\n  worst relative difference anywhere: %.2f%% -> %s" % (worst, res["verdict"]))

    json.dump(res, open(HERE / "results_crosscheck.json", "w"), indent=1)
    print("wrote results_crosscheck.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
