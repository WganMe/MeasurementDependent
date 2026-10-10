#!/usr/bin/env python3
"""
Independent recount of the annual instrument population, straight from the raw
archive. Written to test longitudinal_census.py rather than to reuse it.

The paper claims 41 instruments in 2013 and 706 in 2026. The census script
produced those numbers; this script produces them independently, from the zip
files themselves, using a different parsing approach (csv module over the
extracted member, streaming) and no shared code.

Usage:  python3 independent_recount.py [--years 2013 2026] [--all]
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import pathlib
import re
import zipfile
from collections import defaultdict

ARCHIVE = pathlib.Path(os.environ.get("UO_ARCHIVE")
                       or "/home/bcdr/phd/PhD/urban_observatory/AGGREGATION/none")


def counts_for_year(year: int) -> dict:
    """Return {'ids': set, 'files': int, 'rows': int} for one year.

    NOTE: the archive is NOT depth-consistent. Early years are flat
    (2013/Theme/X.csv.zip) while recent years are nested by month
    (2026/Theme/Month/X.csv.zip). A single fixed-depth glob therefore silently
    finds zero files for one era and looks like a data discrepancy. Use rglob.
    """
    ids: set[str] = set()
    files = rows = 0
    for zpath in sorted((ARCHIVE / str(year)).rglob("*.csv.zip")):
        files += 1
        try:
            with zipfile.ZipFile(zpath) as z:
                for member in z.namelist():
                    if not member.endswith(".csv"):
                        continue
                    with z.open(member) as fh:
                        text = io.TextIOWrapper(fh, encoding="utf-8",
                                                errors="replace", newline="")
                        rdr = csv.DictReader(text)
                        col = None
                        for row in rdr:
                            if col is None:
                                col = "Raw ID" if "Raw ID" in row else None
                                if col is None:
                                    break
                            rows += 1
                            v = (row.get(col) or "").strip()
                            if v:
                                ids.add(v)
        except zipfile.BadZipFile:
            print("    bad zip: %s" % zpath.name)
    return {"ids": ids, "files": files, "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="*", type=int, default=[2013, 2026])
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    years = sorted(int(p.name) for p in ARCHIVE.iterdir()
                   if p.is_dir() and re.fullmatch(r"\d{4}", p.name))
    if not a.all:
        years = [y for y in years if y in a.years]

    print("INDEPENDENT RECOUNT FROM THE RAW ARCHIVE")
    print("archive: %s" % ARCHIVE)
    print("method : csv.DictReader over each zip member, 'Raw ID' column")
    print("=" * 62)
    print("%-6s %-10s %-10s %-12s" % ("year", "files", "rows", "unique IDs"))

    out = {}
    for y in years:
        r = counts_for_year(y)
        out[y] = len(r["ids"])
        print("%-6d %-10d %-10d %-12d" % (y, r["files"], r["rows"], len(r["ids"])))

    # compare with the census result file
    import json
    cen = json.loads(pathlib.Path(
        pathlib.Path(__file__).resolve().parent
        / "uo_census_results.json").read_text())
    claimed = {r["year"]: r["instruments"] for r in cen["per_year"]}

    print("\nCOMPARISON")
    print("%-6s %-14s %-14s %s" % ("year", "census JSON", "recount", "verdict"))
    bad = 0
    for y, n in sorted(out.items()):
        c = claimed.get(y)
        ok = (c == n)
        if not ok:
            bad += 1
        print("%-6d %-14s %-14s %s" % (y, c, n,
                                       "match" if ok else "*** MISMATCH ***"))
    print()
    if bad:
        print("  %d year(s) disagree — the census number is not reproducible "
              "from the archive by an independent route." % bad)
    else:
        print("  every recounted year matches the census JSON.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
