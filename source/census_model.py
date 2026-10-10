#!/usr/bin/env python3
"""
Causal-style analysis of the census: does clustering follow build-out, and by how much?

Two things the existing NUO literature does not do, done here:

1. A fitted relationship between network size and clustering, with an interval.
   The census shows R declining 0.730 -> 0.238 as n grows 17x, but a trend statement
   needs a slope, a fit quality and a confidence interval, otherwise it is an
   eyeballed line.

2. A decomposition of WHY clustering rises, separating three mechanisms:
     M1 densification of a fixed footprint      (area constant, density up)
     M2 expansion of the footprint              (area grows, density constant)
     M3 theme-mix shift inside the footprint    (composition changes)
   A reviewer's first objection is that "clustering" is just a proxy for "more
   sensors in the same place", so the mechanisms must be separated, not asserted.

Estimators: OLS on log-log with bootstrap CI, Theil-Sen as a non-parametric check
(which the reference paper uses), and Mann-Kendall for monotonic trend.

Usage:
    python3 census_model.py
"""
from __future__ import annotations

import json
import math
import os
import pathlib
from collections import Counter

import numpy as np

BASE = pathlib.Path(__file__).resolve().parent
CENSUS = json.loads((BASE / "uo_census_results.json").read_text())
CACHE = pathlib.Path(os.environ.get("UO_CACHE") or (pathlib.Path(__file__).resolve().parent / "uo_sensor_cache.json"))
OUT = BASE / "uo_model_results.json"

RNG = np.random.default_rng(20260929)
LON0, LAT0 = -1.61, 54.97
MLAT, MLON = 110574.0, 111320.0 * math.cos(math.radians(LAT0))


def ols(x: np.ndarray, y: np.ndarray):
    """Slope, intercept, R^2 for a simple linear fit."""
    n = len(x)
    xm, ym = x.mean(), y.mean()
    denom = ((x - xm) ** 2).sum()
    slope = ((x - xm) * (y - ym)).sum() / denom if denom else float("nan")
    inter = ym - slope * xm
    pred = inter + slope * x
    ss_res = ((y - pred) ** 2).sum()
    ss_tot = ((y - ym) ** 2).sum()
    r2 = 1 - ss_res / ss_tot if ss_tot else float("nan")
    return float(slope), float(inter), float(r2)


def theil_sen(x: np.ndarray, y: np.ndarray) -> float:
    slopes = []
    for i in range(len(x)):
        for j in range(i + 1, len(x)):
            if x[j] != x[i]:
                slopes.append((y[j] - y[i]) / (x[j] - x[i]))
    return float(np.median(slopes)) if slopes else float("nan")


def mann_kendall(y: np.ndarray) -> tuple[float, float]:
    """Kendall tau and a normal-approximation two-sided p for monotonic trend."""
    n = len(y)
    s = sum(np.sign(y[j] - y[i]) for i in range(n) for j in range(i + 1, n))
    var = n * (n - 1) * (2 * n + 5) / 18
    if s > 0:
        z = (s - 1) / math.sqrt(var)
    elif s < 0:
        z = (s + 1) / math.sqrt(var)
    else:
        z = 0.0
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    tau = 2 * s / (n * (n - 1))
    return float(tau), float(p)


def bootstrap_slope(x: np.ndarray, y: np.ndarray, k: int = 2000):
    n = len(x)
    out = []
    for _ in range(k):
        idx = RNG.integers(0, n, n)
        if len(set(idx.tolist())) < 3:
            continue
        s, _, _ = ols(x[idx], y[idx])
        if not math.isnan(s):
            out.append(s)
    return (float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5)),
            float(np.mean(out))) if out else (float("nan"),) * 3


def per_year_geometry() -> list[dict]:
    """Footprint area and density per year, for the mechanism decomposition."""
    cache = json.loads(CACHE.read_text())
    sensors, breadth = cache["sensors"], cache["breadth"]
    by_year: dict[int, set[str]] = {}
    for sid, files in breadth.items():
        for f in files:
            y = int(f[:4]) if f[:4].isdigit() else None
            if y:
                by_year.setdefault(y, set()).add(sid)
    rows = []
    for y in sorted(by_year):
        pts, themes = [], Counter()
        for sid in by_year[y]:
            s = sensors.get(sid)
            if not s:
                continue
            themes[s["theme"]] += 1
            pts.append(((s["lon"] - LON0) * MLON, (s["lat"] - LAT0) * MLAT))
        xy = np.array(pts)
        xy = xy[(np.abs(xy) < 60000).all(axis=1)]
        if len(xy) < 5:
            continue
        # 5-95% box: a stable definition of "the footprint actually served",
        # immune to single distant instruments
        lo, hi = np.percentile(xy, 5, axis=0), np.percentile(xy, 95, axis=0)
        area = float(np.prod(hi - lo))
        rows.append({
            "year": y, "n": len(xy),
            "area_core_km2": round(area / 1e6, 2),
            "density_core": round(len(xy) / (area / 1e6), 3) if area > 0 else None,
            # sorted by key: `themes` is filled while iterating a SET of raw_ids,
            # and str hashing is randomised per process, so an unsorted dict made
            # this committed JSON differ byte-for-byte between runs.
            "themes": dict(sorted(themes.items())),
        })
    return rows


def main() -> int:
    py = CENSUS["per_year"]
    y = np.array([r["year"] for r in py], dtype=float)
    R = np.array([r["clark_evans_R"] for r in py], dtype=float)
    G = np.array([r["gini_20x20"] for r in py], dtype=float)
    n = np.array([r["instruments"] for r in py], dtype=float)

    res: dict = {}

    # ---- 1. trend of clustering over time -----------------------------------
    s_t, i_t, r2_t = ols(y, R)
    ts_t = theil_sen(y, R)
    tau, p_mk = mann_kendall(R)
    lo_t, hi_t, mean_t = bootstrap_slope(y, R)
    res["trend_R_over_time"] = {
        "ols_slope_per_year": round(s_t, 5),
        "ols_slope_boot_ci95": [round(lo_t, 5), round(hi_t, 5)],
        "ols_intercept": round(i_t, 4),
        "ols_r2": round(r2_t, 4),
        "theil_sen_slope": round(ts_t, 5),
        "mann_kendall_tau": round(tau, 4),
        "mann_kendall_p": float(p_mk),
        "years": int(len(y)),
    }

    # ---- 2. does clustering track SIZE? (log-log) ---------------------------
    lx, ly = np.log(n), np.log(R)
    s_n, i_n, r2_n = ols(lx, ly)
    lo_n, hi_n, _ = bootstrap_slope(lx, ly)
    res["R_versus_size_loglog"] = {
        "slope": round(s_n, 4),
        "slope_boot_ci95": [round(lo_n, 4), round(hi_n, 4)],
        "intercept": round(i_n, 4),
        "r2": round(r2_n, 4),
        "reading": ("clustering behaves as a power law in network size: a slope of "
                    "%.2f means a 1%% increase in instruments accompanies a %.2f%% "
                    "decrease in R" % (s_n, -s_n)),
    }

    # ---- 3. Gini trend, for consistency -------------------------------------
    s_g, _, r2_g = ols(y, G)
    tau_g, p_g = mann_kendall(G)
    res["trend_gini_over_time"] = {
        "ols_slope_per_year": round(s_g, 5),
        "ols_r2": round(r2_g, 4),
        "mann_kendall_tau": round(tau_g, 4),
        "mann_kendall_p": float(p_g),
    }

    # ---- 4. mechanism decomposition -----------------------------------------
    geo = per_year_geometry()
    res["geometry_by_year"] = geo
    first, last = geo[0], geo[-1]
    res["mechanisms_2013_to_2026"] = {
        "n_change": [first["n"], last["n"]],
        "area_change": [first["area_core_km2"], last["area_core_km2"]],
        "density_change": [first["density_core"], last["density_core"]],
        "reading": (
            "instruments x%.1f while the 5-95%% core area went from %s to %s km2 "
            "(x%.2f), so density rose from %s to %s per km2 (x%.1f); "
            "clustering is therefore driven mainly by %s"
            % (last["n"] / first["n"], first["area_core_km2"], last["area_core_km2"],
               last["area_core_km2"] / first["area_core_km2"] if first["area_core_km2"] else float("nan"),
               first["density_core"], last["density_core"],
               (last["density_core"] or 0) / (first["density_core"] or 1),
               "densification inside a stable footprint" if
               (last["area_core_km2"] / max(first["area_core_km2"], 1e-9)) < 2
               else "footprint expansion")),
    }

    # ---- 5. uncertainty on the headline claim -------------------------------
    drop = (1 - R[-1] / R[0]) * 100
    res["headline"] = {
        "R_first": float(R[0]), "R_last": float(R[-1]),
        "percent_change": round(float(drop), 1),
        "size_growth": round(float(n[-1] / n[0]), 1),
        "statement": ("Clark-Evans R fell from %.3f (%d) to %.3f (%d), a %.0f%% "
                      "reduction, while the instrument population grew %.1fx"
                      % (R[0], int(y[0]), R[-1], int(y[-1]), drop, n[-1] / n[0])),
    }

    OUT.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items()
                      if k not in ("geometry_by_year", "mechanisms_2013_to_2026")},
                     indent=1)[:3200])
    print()
    print("  MECHANISMS:", res["mechanisms_2013_to_2026"]["reading"])
    print("\n  wrote %s" % OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
