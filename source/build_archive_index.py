#!/usr/bin/env python3
"""
Build a single per-year index of the archive, once, so every
analysis reads from a cheap local file instead of re-walking 69 GB of zips.

Output: uo_archive_index.json
{
  "built": "<timestamp>",
  "years": {
    "2013": {
      "identifiers": {"<raw_id>": [lon, lat, "Theme/Variable", "YYYY-MM-DD"]},
      "files": N
    }, ...
  }
}

The first coordinate and the first theme/variable seen for an identifier in a year
are kept. `min_date` is the earliest timestamp seen, which lets the partial-2026
check be done without re-reading the archive.

Usage:  python3 build_archive_index.py [--out uo_archive_index.json]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import pathlib
import sys
import zipfile
from datetime import datetime, timezone

# The 69 GB Newcastle archive is NOT redistributed with this repository, so this
# script cannot run from the clone alone -- it needs the collection itself.
# Set UO_ARCHIVE to point at your own copy (the directory holding 2013/ .. 2026/).
ARCHIVE = pathlib.Path(os.environ.get("UO_ARCHIVE")
                       or "/home/bcdr/phd/PhD/urban_observatory/AGGREGATION/none")
HERE = pathlib.Path(__file__).resolve().parent


def parse_ts(s: str) -> str:
    """Return YYYY-MM-DD from a variety of ISO-ish timestamps, else ''."""
    s = (s or "").strip()
    if len(s) < 10:
        return ""
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return s[:10] if s[4] == "-" else ""


def build(year: int) -> dict:
    """
    One pass over the year. csv.reader with column indices, not DictReader: the
    archive is ~8.4 million rows per year even in its early years, and per-row
    dict construction was the bottleneck (75 s per year).
    """
    ids: dict[str, list] = {}
    months: set[str] = set()
    files = 0
    for z in sorted((ARCHIVE / str(year)).rglob("*.csv.zip")):
        files += 1
        theme = z.parent.name
        try:
            with zipfile.ZipFile(z) as zf:
                for member in zf.namelist():
                    if not member.endswith(".csv"):
                        continue
                    with zf.open(member) as fh:
                        t = io.TextIOWrapper(fh, encoding="utf-8",
                                             errors="replace", newline="")
                        rdr = csv.reader(t)
                        try:
                            head = next(rdr)
                        except StopIteration:
                            continue
                        try:
                            i_id = head.index("Raw ID")
                            i_lat = head.index("Sensor Centroid Latitude")
                            i_lon = head.index("Sensor Centroid Longitude")
                            i_ts = head.index("Timestamp")
                        except ValueError:
                            continue
                        for row in rdr:
                            if len(row) <= max(i_id, i_lat, i_lon, i_ts):
                                continue
                            i = row[i_id].strip()
                            if not i:
                                continue
                            ts = row[i_ts].strip()[:10]
                            if ts:
                                months.add(ts[:7])
                            old = ids.get(i)
                            if old is None:
                                la, lo = row[i_lat].strip(), row[i_lon].strip()
                                try:
                                    lat = float(la) if la else None
                                    lon = float(lo) if lo else None
                                except ValueError:
                                    lat = lon = None
                                ids[i] = [lon, lat, "%s/%s" % (theme, member), ts]
                            elif ts and (not old[3] or ts < old[3]):
                                old[3] = ts
        except zipfile.BadZipFile:
            print("  bad zip: %s" % z.name, file=sys.stderr)
    return {"identifiers": ids, "files": files, "months": sorted(months)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "uo_archive_index.json"))
    a = ap.parse_args()

    out = {"built": datetime.now(timezone.utc).isoformat(), "years": {}}
    total_files = 0
    for y in range(2013, 2027):
        print("reading %d ..." % y, flush=True)
        d = build(y)
        out["years"][str(y)] = d
        total_files += d["files"]
        print("  %d: %d files, %d identifiers"
              % (y, d["files"], len(d["identifiers"])), flush=True)

    out["total_files"] = total_files
    pathlib.Path(a.out).write_text(json.dumps(out))
    print("\nwritten %s" % a.out)
    print("total files indexed: %d" % total_files)
    print("size: %.1f MB" % (pathlib.Path(a.out).stat().st_size / 1e6))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
