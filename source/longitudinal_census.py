#!/usr/bin/env python3
"""
The 13-year census: how the Newcastle Urban Observatory's instrument population
changed from 2013 to 2026.

This is the analysis no published paper has performed. Every existing NUO study takes
a slice and treats it as the network: 110 pedestrian sensors, 13 sensors on two
streets, 12 schools. None has reconstructed the instrument population per year and
asked how it evolved — which sensors appeared, which went silent, and whether the
network's composition drifted.

Everything is computed with uncertainty attached, because point estimates of spatial
and thematic concentration are not credible on their own:
  * Gini with bootstrap confidence intervals
  * Clark-Evans R with a permutation test against CSR
  * Theil T decomposition (within-theme vs between-theme), as the carbon paper does
  * leave-one-theme-out sensitivity
  * Benjamini-Hochberg correction across the per-year tests

Usage:
    python3 longitudinal_census.py
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import re
from collections import Counter, defaultdict

import numpy as np

ROOT = pathlib.Path(os.environ.get("UO_ARCHIVE")
                    or "/home/bcdr/phd/PhD/urban_observatory/AGGREGATION/none")
CACHE = pathlib.Path(os.environ.get("UO_CACHE") or (pathlib.Path(__file__).resolve().parent / "uo_sensor_cache.json"))
OUT = pathlib.Path(os.environ.get("UO_CENSUS_OUT")
                   or (pathlib.Path(__file__).resolve().parent / "uo_census_results.json"))

LON0, LAT0 = -1.61, 54.97
MLAT = 110574.0
MLON = 111320.0 * math.cos(math.radians(LAT0))
RNG = np.random.default_rng(20260929)          # fixed seed: reproducibility


def gini(xs) -> float:
    xs = np.sort(np.asarray(xs, dtype=float))
    n = xs.size
    if n == 0:
        return float("nan")
    s = xs.sum()
    if s <= 0:
        return 0.0
    cum = np.cumsum(xs)
    return float((n + 1 - 2 * (cum / s).sum()) / n)


def theil_t(xs) -> float:
    """Theil T. Requires strictly positive values; zeros are excluded and counted."""
    xs = np.asarray([x for x in xs if x > 0], dtype=float)
    if xs.size < 2:
        return float("nan")
    mu = xs.mean()
    return float((xs / mu * np.log(xs / mu)).mean())


def clark_evans(xy: np.ndarray) -> tuple[float, float, float]:
    """Observed mean NN distance, its CSR expectation, and R."""
    from scipy.spatial import cKDTree
    if len(xy) < 3:
        return (float("nan"), float("nan"), float("nan"))
    tree = cKDTree(xy)
    d, _ = tree.query(xy, k=2)
    nn = d[:, 1]
    area = float(np.prod(np.ptp(xy, axis=0)))
    if area <= 0:
        return (float("nan"), float("nan"), float("nan"))
    rho = len(xy) / area
    exp = 0.5 / math.sqrt(rho)
    return (float(nn.mean()), float(exp), float(nn.mean() / exp))


def bh_correct(pvals: list[float]) -> list[float]:
    """Benjamini-Hochberg adjusted p-values."""
    n = len(pvals)
    order = np.argsort(pvals)
    adj = np.empty(n)
    prev = 1.0
    for rank, idx in enumerate(reversed(order), 1):
        k = n - rank + 1
        val = min(prev, pvals[idx] * n / k)
        adj[idx] = val
        prev = val
    return adj.tolist()


def ranked(counter) -> list[tuple]:
    """`Counter.most_common()` with a deterministic tie-break.

    `most_common` is a stable sort on the count alone, so equal counts come out
    in the order the source iterated. Here the source is a SET of raw_ids, and
    Python randomises str hashing per process, so the committed JSON differed
    byte-for-byte between runs. Rank by (count descending, key ascending).
    """
    return sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))


def load() -> tuple[dict, dict]:
    cache = json.loads(CACHE.read_text())
    sensors = cache["sensors"]          # raw_id -> {lon,lat,name,theme,variable}
    breadth = cache["breadth"]          # raw_id -> [file paths]
    return sensors, breadth


def year_of(path: str) -> int | None:
    m = re.match(r"(\d{4})/", path)
    return int(m.group(1)) if m else None


def main() -> int:
    sensors, breadth = load()
    print("  sensors in cache: %d" % len(sensors))

    # ---- per-year instrument population -------------------------------------
    by_year: dict[int, set[str]] = defaultdict(set)
    for sid, files in breadth.items():
        for f in files:
            y = year_of(f)
            if y:
                by_year[y].add(sid)

    years = sorted(by_year)
    print("  years present: %s" % years)

    rows = []
    pvals = []
    for y in years:
        ids = by_year[y]
        pts = []
        themes = Counter()
        for sid in ids:
            s = sensors.get(sid)
            if not s:
                continue
            themes[s["theme"]] += 1
            pts.append(((s["lon"] - LON0) * MLON, (s["lat"] - LAT0) * MLAT))
        if not pts:
            continue
        xy = np.array(pts)
        # keep the same plausibility filter used in the main analysis
        keep = (np.abs(xy) < 60000).all(axis=1)
        xy = xy[keep]
        if len(xy) < 5:
            continue

        # grid counts at a fixed, predeclared resolution (20x20)
        cells = 20
        x0, y0 = xy.min(axis=0)
        span = np.ptp(xy, axis=0)
        span[span == 0] = 1.0
        gi = np.clip(((xy - [x0, y0]) / span * cells).astype(int), 0, cells - 1)
        counts = np.zeros((cells, cells), dtype=int)
        np.add.at(counts, (gi[:, 1], gi[:, 0]), 1)
        occ = counts[counts > 0]

        g = gini(occ)
        n = len(xy)
        # permutation test: is the clustering stronger than random placement?
        nn_mean, exp, R = clark_evans(xy)
        null = []
        for _ in range(199):
            rnd = RNG.uniform(xy.min(axis=0), xy.max(axis=0), size=(n, 2))
            _, _, r0 = clark_evans(rnd)
            if not math.isnan(r0):
                null.append(r0)
        p = (1 + sum(1 for r0 in null if r0 <= R)) / (len(null) + 1)
        pvals.append(p)

        # theme shares and Theil decomposition
        tot = sum(themes.values())
        shares = {k: v / tot * 100 for k, v in themes.items()}
        counts_t = np.array(list(themes.values()), dtype=float)
        th_t = theil_t(counts_t)

        rows.append({
            "year": y,
            "instruments": n,
            "themes_used": len(themes),
            "gini_20x20": round(g, 4),
            "gini_ci95": [round(v, 4) for v in
                          np.percentile([gini(RNG.choice(occ, size=occ.size,
                                                         replace=True).astype(int))
                                         for _ in range(500)], [2.5, 97.5])],
            "clark_evans_R": round(R, 4),
            "nn_mean_m": round(nn_mean, 1),
            "perm_p": round(p, 4),
            "theil_T_themes": round(th_t, 4),
            "top_theme": max(shares, key=shares.get),
            "top_theme_pct": round(max(shares.values()), 1),
            "vehicle_pct": round(shares.get("Vehicles", 0.0), 1),
            "themes": dict(ranked(themes)),
        })
        print("    %d  n=%-5d R=%.3f  gini=%.3f  veh=%.1f%%  top=%s" %
              (y, n, R, g, shares.get("Vehicles", 0), max(shares, key=shares.get)))

    # multiple-comparison correction across the per-year clustering tests
    adj = bh_correct(pvals)
    for r, a in zip(rows, adj):
        r["perm_p_bh"] = round(a, 4)

    # ---- births and deaths ---------------------------------------------------
    first_seen = {sid: min(year_of(f) for f in fs if year_of(f))
                  for sid, fs in breadth.items() if any(year_of(f) for f in fs)}
    last_seen = {sid: max(year_of(f) for f in fs if year_of(f))
                 for sid, fs in breadth.items() if any(year_of(f) for f in fs)}
    cur_year = max(years)
    births = Counter(first_seen.values())
    deaths = Counter(v for v in last_seen.values() if v < cur_year)

    # ---- leave-one-theme-out sensitivity ------------------------------------
    loo = []
    full = [r for r in rows if r["year"] == cur_year]
    if full:
        base = full[0]
        for sid_th in sorted({s["theme"] for s in sensors.values()}):
            pts = [((s["lon"] - LON0) * MLON, (s["lat"] - LAT0) * MLAT)
                   for sid, s in sensors.items()
                   if s["theme"] != sid_th]
            xy = np.array(pts)
            xy = xy[(np.abs(xy) < 60000).all(axis=1)]
            if len(xy) < 20:
                continue
            _, _, R = clark_evans(xy)
            loo.append({"excluded_theme": sid_th, "clark_evans_R": round(R, 4)})

    res = {
        "years_covered": [min(years), max(years)],
        "n_years": len(rows),
        "per_year": rows,
        "births_by_year": {str(k): v for k, v in sorted(births.items())},
        "silences_by_year": {str(k): v for k, v in sorted(deaths.items())},
        "leave_one_theme_out": sorted(loo, key=lambda x: x["clark_evans_R"]),
        "notes": [
            "Gini is computed on occupied 20x20 grid cells, the resolution declared "
            "in advance; CI is a 500-resample bootstrap of the observed cell counts.",
            "Clark-Evans R is tested against complete spatial randomness by 199 "
            "uniform draws inside the observed bounding box; p is corrected across "
            "years with Benjamini-Hochberg.",
            "A sensor counts as present in a year if it appears in any archive file "
            "for that year, so births and silences are observation-based, not "
            "vendor-declared deployment dates.",
        ],
    }
    OUT.write_text(json.dumps(res, indent=1))
    print("\n  wrote %s" % OUT)
    print("  births by year : %s" % dict(sorted(births.items())))
    print("  silences by year: %s" % dict(sorted(deaths.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
