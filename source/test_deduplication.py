#!/usr/bin/env python3
"""
The deduplicated unit, tested directly.

Claim: multi-identifier co-located devices give nearest-neighbour distance zero,
mechanically depressing Clark-Evans R, and if the share of co-located locations
grew over time then the "clustering" trend is a reporting artifact.

Test: recompute the annual Clark-Evans R twice, from the raw archive, with
  (a) every identifier counted, and
  (b) each distinct coordinate counted once,
and compare the two trajectories. If R(b) shows the same decline, the finding is
not an artifact of the unit of analysis.

Usage:  python3 test_deduplication.py
"""
from __future__ import annotations

import csv
import io
import math
import pathlib
import zipfile
from collections import defaultdict

ARCHIVE = pathlib.Path("/home/bcdr/phd/PhD/urban_observatory/AGGREGATION/none")
LAT0, LON0, R = 54.97, -1.61, 6371000.0
# 5-95% core, as the manuscript reports it for 2013 and 2026
CORE2013_KM2, CORE2026_KM2 = 335.02, 527.71


def proj(lat, lon):
    x = math.radians(lon - LON0) * R * math.cos(math.radians(LAT0))
    y = math.radians(lat - LAT0) * R
    return x, y


def year_points(year):
    """Return {identifier: (x, y)} for one year, first coordinate seen wins."""
    pts = {}
    for z in sorted((ARCHIVE / str(year)).rglob("*.csv.zip")):
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
                            if abs(x) < 60000 and abs(y) < 60000:
                                pts[i] = (x, y)
        except zipfile.BadZipFile:
            pass
    return pts


def clark_evans(xs, ys, lo, hi):
    """R = mean NN distance / expected. Rectangular bounding box of the points
    (a proxy for the reported core, applied identically to both variants)."""
    n = len(xs)
    if n < 3:
        return None, None
    area = lo * hi * 4.0          # full side lengths = 2*lo, 2*hi
    if area <= 0:
        return None, None
    rho = n / area
    d = []
    for i in range(n):
        best = float("inf")
        for j in range(n):
            if i == j:
                continue
            dx, dy = xs[i] - xs[j], ys[i] - ys[j]
            dd = dx * dx + dy * dy
            if dd < best:
                best = dd
        d.append(math.sqrt(best))
    mean_d = sum(d) / n
    exp_d = 1.0 / (2.0 * math.sqrt(rho))       # in metres
    return mean_d / exp_d, sum(d) / n


def main() -> int:
    years = list(range(2013, 2027))
    print("CLARK-EVANS: all identifiers vs unique locations")
    print("=" * 74)
    print("%-6s %-6s %-6s %-14s %-6s %-14s %-8s"
          % ("year", "IDs", "locs", "R(all ids)", "R(locs)", "dup share", "note"))
    rows = []
    for y in years:
        pts = year_points(y)
        ids = list(pts.items())
        if len(ids) < 3:
            print("%-6d %-6d %-6d  (too few points)" % (y, len(ids), len(set(pts.values()))))
            continue
        # (a) every identifier
        xa = [p[0] for _, p in ids]
        ya = [p[1] for _, p in ids]
        # bounding half-extents from the data
        lo_a = max(abs(min(xa)), abs(max(xa)))
        hi_a = max(abs(min(ya)), abs(max(ya)))
        Ra, _ = clark_evans(xa, ya, lo_a, hi_a)

        # (b) unique coordinates
        uniq = {}
        for k, p in ids:
            uniq.setdefault((round(p[0], 2), round(p[1], 2)), p)
        ux = [p[0] for p in uniq.values()]
        uy = [p[1] for p in uniq.values()]
        lo_b = max(abs(min(ux)), abs(max(ux)))
        hi_b = max(abs(min(uy)), abs(max(uy)))
        Rb, _ = clark_evans(ux, uy, lo_b, hi_b)

        share = 100.0 * (len(ids) - len(uniq)) / len(ids) if ids else 0
        rows.append((y, len(ids), len(uniq), Ra, Rb, share))
        print("%-6d %-6d %-6d %-14.4f %-6d %-14.4f %-8.1f%%"
              % (y, len(ids), len(uniq), Ra, len(uniq), Rb, share))

    print()
    if rows:
        f, l = rows[0], rows[-1]
        print("  FIRST year  %d: R(ids)=%.4f  R(locs)=%.4f" % (f[0], f[3], f[4]))
        print("  LAST  year  %d: R(ids)=%.4f  R(locs)=%.4f" % (l[0], l[3], l[4]))
        da = 100 * (f[3] - l[3]) / f[3]
        db = 100 * (f[4] - l[4]) / f[4]
        print("  decline, all identifiers : %.1f%%" % da)
        print("  decline, unique locations: %.1f%%" % db)
        print("  duplicate share first -> last: %.1f%% -> %.1f%%" % (f[5], l[5]))
        print()
        if db > 0.5 * da:
            print("  VERDICT: the decline survives deduplication (%.1f%% vs %.1f%%)."
                  % (db, da))
            print("           The concern is worth reporting but does not")
            print("           explain the headline.")
        else:
            print("  VERDICT: the decline does NOT survive deduplication.")
            print("           The headline must change to the deduplicated unit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
