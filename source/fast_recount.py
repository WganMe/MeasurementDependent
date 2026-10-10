#!/usr/bin/env python3
"""
Fast, independent recount and a deduplication test.

Replaces the earlier O(n^2) attempts, which were reading 69 GB of zips and then
doing 706^2 distance computations per year. This version uses scipy.cKDTree, so
the whole archive pass is dominated by zip I/O rather than arithmetic, and it
prints incrementally so progress is visible.

It answers three questions at once, all from the raw archive:
  1. instruments per year                       (independent of the census script)
  2. Clark-Evans R with every identifier        (the manuscript's convention)
  3. Clark-Evans R with unique coordinates      (deduplicated unit)
plus the duplicate share per year, which is what decides whether the headline is
an artifact of the unit of analysis.

Usage:  python3 fast_recount.py [--years 2013 2026]
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import pathlib
import sys
import zipfile

import numpy as np
from scipy.spatial import cKDTree

ARCHIVE = pathlib.Path("/home/bcdr/phd/PhD/urban_observatory/AGGREGATION/none")
LAT0, LON0, R = 54.97, -1.61, 6371000.0
LIMIT_M = 60000.0


def proj(lat: float, lon: float) -> tuple[float, float]:
    x = math.radians(lon - LON0) * R * math.cos(math.radians(LAT0))
    y = math.radians(lat - LAT0) * R
    return x, y


def year_points(year: int) -> dict[str, tuple[float, float]]:
    """identifier -> (x, y) in metres. First coordinate seen wins."""
    pts: dict[str, tuple[float, float]] = {}
    files = 0
    for z in sorted((ARCHIVE / str(year)).rglob("*.csv.zip")):
        files += 1
        try:
            with zipfile.ZipFile(z) as zf:
                for member in zf.namelist():
                    if not member.endswith(".csv"):
                        continue
                    with zf.open(member) as fh:
                        t = io.TextIOWrapper(fh, encoding="utf-8",
                                             errors="replace", newline="")
                        for row in csv.DictReader(t):
                            i = (row.get("Raw ID") or "").strip()
                            if not i or i in pts:
                                continue
                            la = (row.get("Sensor Centroid Latitude") or "").strip()
                            lo = (row.get("Sensor Centroid Longitude") or "").strip()
                            if not la or not lo:
                                continue
                            try:
                                lat, lon = float(la), float(lo)
                            except ValueError:
                                continue
                            x, y = proj(lat, lon)
                            if abs(x) < LIMIT_M and abs(y) < LIMIT_M:
                                pts[i] = (x, y)
        except zipfile.BadZipFile:
            pass
    return pts


def clark_evans(P: np.ndarray, area_m2: float | None = None) -> tuple[float, float]:
    """R and mean NN distance. Area defaults to the points' bounding box."""
    n = len(P)
    if n < 3:
        return float("nan"), float("nan")
    tree = cKDTree(P)
    d, _ = tree.query(P, k=2)          # first neighbour is the point itself
    nn = d[:, 1]
    mean_nn = float(np.mean(nn))
    if area_m2 is None:
        w = float(P[:, 0].max() - P[:, 0].min())
        h = float(P[:, 1].max() - P[:, 1].min())
        area_m2 = w * h
    if area_m2 <= 0:
        return float("nan"), mean_nn
    rho = n / area_m2
    expected = 1.0 / (2.0 * math.sqrt(rho))
    return mean_nn / expected, mean_nn


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="*", type=int,
                    default=list(range(2013, 2027)))
    a = ap.parse_args()

    print("INDEPENDENT RECOUNT + DEDUPLICATION TEST")
    print("archive: %s" % ARCHIVE)
    print("metric : scipy cKDTree nearest neighbour, 60 km filter applied")
    print("=" * 82)
    print("%-6s %-7s %-7s %-11s %-11s %-9s %-9s"
          % ("year", "IDs", "locs", "R(all ids)", "R(unique)", "dup%", "meanNN m"))

    rows = []
    for y in sorted(a.years):
        pts = year_points(y)
        if len(pts) < 3:
            print("%-6d %-7d  (too few points)" % (y, len(pts)))
            continue
        keys = list(pts)
        A = np.array([pts[k] for k in keys], dtype=float)
        Ra, mnn = clark_evans(A)

        # deduplicate: collapse coordinates to a 1 m grid
        grid: dict[tuple[int, int], tuple[float, float]] = {}
        for k in keys:
            x, y = pts[k]
            grid.setdefault((int(round(x)), int(round(y))), (x, y))
        B = np.array(list(grid.values()), dtype=float)
        Rb, _ = clark_evans(B)

        dup = 100.0 * (len(keys) - len(B)) / len(keys)
        rows.append((y, len(keys), len(B), Ra, Rb, dup))
        print("%-6d %-7d %-7d %-11.4f %-11.4f %-9.1f %-9.0f"
              % (y, len(keys), len(B), Ra, Rb, dup, mnn))
        sys.stdout.flush()

    print()
    if rows:
        f, l = rows[0], rows[-1]
        da = 100 * (f[3] - l[3]) / f[3]
        db = 100 * (f[4] - l[4]) / f[4]
        print("  first year %d : R(all)=%.4f  R(unique)=%.4f" % (f[0], f[3], f[4]))
        print("  last  year %d : R(all)=%.4f  R(unique)=%.4f" % (l[0], l[3], l[4]))
        print("  decline, all identifiers   : %.1f%%" % da)
        print("  decline, unique locations  : %.1f%%" % db)
        print("  duplicate share            : %.1f%% -> %.1f%%" % (f[5], l[5]))
        print("  instrument growth          : %.2fx" % (l[1] / f[1]))
        print("  location growth            : %.2fx" % (l[2] / f[2]))
        print()
        if db > 0.5 * da:
            print("  VERDICT: the decline SURVIVES deduplication.")
        else:
            print("  VERDICT: the decline does NOT survive deduplication; the")
            print("           the deduplicated unit changes the headline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
