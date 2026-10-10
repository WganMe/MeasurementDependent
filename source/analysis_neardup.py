#!/usr/bin/env python3
"""The near-duplicate (tolerance-deduplication) test.

WHY THIS EXISTS. Section 3.4 of the main text says that whether the late
separation from the size-matched reference is "rearrangement" or "a change in how
the structure is registered is the subject of the near-duplicate test below". No
such test was run. It is also the likeliest reconciliation between the two
size-matched references, which disagree:

  * thinning the 2026 network to each year's size takes R from 0.202 at n = 561 to
    0.387 at n = 39, so size alone reproduces the whole 2013-2026 decline;
  * drawing subsets of the pooled footprint is flat in n (0.449 -> 0.436).

A candidate explanation is that the recent years contain tight PAIRS of
instruments whose coordinates differ by a few metres -- separate identifiers at
the same installation -- which depress R at large n and which thinning breaks up.
Tolerance deduplication removes exactly those pairs. If the decline is a
registration artefact, it should weaken or vanish as the tolerance widens. If it
is geographic, it should survive.

METHOD. Greedy spatial clustering at a radius r (single-linkage on a KD-tree
graph), keeping the first identifier encountered in each cluster. Then recompute,
per year:
  * distinct sites and R on the fixed full-record hull,
  * the 2013-2026 slope on year,
for r in {0 (exact), 5, 10, 25} m. Exact deduplication reproduces the published
location series, which is the control on this script.

Also reports, per year, how many clusters merge (identifiers removed) at each
tolerance, and re-runs the pooled size-matched reference on the r = 25 m
deduplicated footprint, so the effect on Table 5 can be read directly.

Writes: results_neardup.json

Usage: python3 analysis_neardup.py
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
from scipy.spatial import ConvexHull, cKDTree

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analysis_common import load_years, ce_r  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
RNG = np.random.default_rng(20261003)
TOLS = [0.0, 5.0, 10.0, 25.0]
N_POOLED_DRAWS = 400


def dedup(P: np.ndarray, r: float) -> np.ndarray:
    """Greedy single-linkage clustering at radius r; keep one point per cluster.

    r = 0 reduces to exact coordinate dedup after rounding, which is the
    published location series.
    """
    if len(P) == 0:
        return P
    if r <= 0:
        return np.unique(np.round(P, 3), axis=0)
    tree = cKDTree(P)
    pairs = tree.query_pairs(r, output_type="ndarray")
    parent = np.arange(len(P))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, j in pairs:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)
    roots = np.array([find(i) for i in range(len(P))])
    _, first = np.unique(roots, return_index=True)
    return P[np.sort(first)]


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)

    allP = np.vstack([np.array([(v[0], v[1]) for v in yrs[y].values()], float)
                      for y in years])
    A_hull = float(ConvexHull(allP).volume)
    print("hull area %.1f km^2" % (A_hull / 1e6))

    res: dict = {"hull_area_m2": A_hull, "tolerances_m": TOLS,
                 "n_pooled_draws": N_POOLED_DRAWS, "per_tol": {}}

    for r in TOLS:
        rows = []
        for y in years:
            raw = np.array([(v[0], v[1]) for v in yrs[y].values()], float)
            P = dedup(raw, r)
            rows.append({"year": y, "n_raw": len(raw), "n_sites": len(P),
                         "merged": len(raw) - len(P), "R": ce_r(P, A_hull)})
        R = np.array([d["R"] for d in rows])
        b = np.polyfit(years, R, 1)
        resid = R - np.polyval(b, years)
        n = len(years)
        se = float(np.sqrt(np.sum(resid ** 2) / (n - 2)
                           / np.sum((np.array(years) - np.mean(years)) ** 2)))
        from scipy import stats
        p = float(2 * stats.t.sf(abs(b[0] / se), n - 2))
        fall = 100.0 * (R[0] - R[-1]) / R[0]

        label = "exact (published)" if r == 0 else "%g m" % r
        print("\n[%s]  slope %+.5f /yr (p = %.4f)   2013 %.3f -> 2026 %.3f  = %.1f%% fall"
              % (label, b[0], p, R[0], R[-1], fall))
        print("   year   ids  sites  merged    R")
        for d in rows:
            print("   %d %5d %6d %7d  %.3f"
                  % (d["year"], d["n_raw"], d["n_sites"], d["merged"], d["R"]))

        entry = {"rows": rows, "slope": float(b[0]), "ols_se": se, "ols_p": p,
                 "fall_pct": float(fall), "R_first": float(R[0]),
                 "R_last": float(R[-1]),
                 "merged_total": int(sum(d["merged"] for d in rows))}

        # pooled size-matched reference on this tolerance, so Table 5 can be re-read
        pool = dedup(np.vstack([np.array([(v[0], v[1]) for v in yrs[y].values()], float)
                                for y in years]), r)
        prows = []
        for y in years:
            obs = ce_r(dedup(np.array([(v[0], v[1]) for v in yrs[y].values()], float), r),
                       A_hull)
            nn = len(dedup(np.array([(v[0], v[1]) for v in yrs[y].values()], float), r))
            draws = np.array([ce_r(pool[RNG.choice(len(pool), nn, replace=False)], A_hull)
                              for _ in range(N_POOLED_DRAWS)])
            prows.append({"year": y, "n": nn, "R_obs": obs,
                          "R_pooled": float(draws.mean()),
                          "sd": float(draws.std(ddof=1)),
                          "z": float((obs - draws.mean()) / draws.std(ddof=1))})
        entry["pooled"] = prows
        entry["pooled_n_sites"] = len(pool)
        zs = [d["z"] for d in prows]
        print("   pooled reference: n_sites %d, z range %+.2f .. %+.2f, 2026 z %+.2f"
              % (len(pool), min(zs), max(zs), prows[-1]["z"]))

        res["per_tol"][label] = entry

    out = HERE / "results_neardup.json"
    out.write_text(json.dumps(res, indent=1))
    print("\nwrote %s" % out.name)

    # ---- verdict -----------------------------------------------------------
    e0 = res["per_tol"]["exact (published)"]
    e25 = res["per_tol"]["25 m"]
    print("\nVERDICT")
    print("  exact  : slope %+.5f  fall %.1f%%  2026 z %+.2f"
          % (e0["slope"], e0["fall_pct"], e0["pooled"][-1]["z"]))
    print("  25 m   : slope %+.5f  fall %.1f%%  2026 z %+.2f"
          % (e25["slope"], e25["fall_pct"], e25["pooled"][-1]["z"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
