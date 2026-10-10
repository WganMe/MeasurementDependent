#!/usr/bin/env python3
"""
Reproduce the provenance audit from the sources instead of trusting the prose.

The manuscript states: the frozen snapshot holds 1411 identifiers, covering 64.6%
of the instruments that ever reported; 674 are absent; 63.5% of the omitted ones
are vehicle counters.

64.6% of 1906 is ~1232, so ~179 snapshot
identifiers should be absent from the census. That discrepancy is not mentioned
anywhere. This script recomputes the whole comparison from
  - the snapshot: urban_observatory.db  (table `sensors`, column raw_id)
  - our census:  the raw archive
and prints both the intersection and the two set differences.

Usage:  python3 reproduce_snapshot_audit.py
"""
from __future__ import annotations

import csv
import io
import pathlib
import sqlite3
import zipfile
from collections import Counter

ARCHIVE = pathlib.Path("/home/bcdr/phd/PhD/urban_observatory/AGGREGATION/none")
DBS = [
    pathlib.Path("/home/bcdr/phd/delivery_paper2/urban-observatory-benchmark-rag/urban_observatory.db"),
    pathlib.Path("/home/bcdr/phd/phd_data_export/urban_observatory.db"),
]


def snapshot_ids(db: pathlib.Path) -> dict[str, dict]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    cols = [r[1] for r in con.execute("PRAGMA table_info(sensors)")]
    out = {}
    for row in con.execute("SELECT * FROM sensors"):
        d = dict(row)
        rid = str(d.get("raw_id") or "").strip()
        if rid:
            out[rid] = d
    con.close()
    return out, cols


def archive_ids() -> dict[str, set]:
    """identifier -> set of themes it appears under, from every year."""
    ids: dict[str, set] = {}
    for year in range(2013, 2027):
        for z in sorted((ARCHIVE / str(year)).rglob("*.csv.zip")):
            theme = z.parent.name if z.parent.name.isalpha() else "?"
            try:
                with zipfile.ZipFile(z) as zf:
                    for m in zf.namelist():
                        if not m.endswith(".csv"):
                            continue
                        with zf.open(m) as fh:
                            t = io.TextIOWrapper(fh, encoding="utf-8",
                                                 errors="replace", newline="")
                            for row in csv.DictReader(t):
                                i = (row.get("Raw ID") or "").strip()
                                if i:
                                    ids.setdefault(i, set()).add(theme)
            except zipfile.BadZipFile:
                pass
    return ids


def main() -> int:
    snap, cols = snapshot_ids(DBS[0])
    print("FROZEN SNAPSHOT")
    print("=" * 70)
    print("  db            : %s" % DBS[0].name)
    print("  sensors table : %d rows" % len(snap))
    print("  columns       : %s" % ", ".join(cols))
    print()

    print("archiving census identifiers ...")
    arch = archive_ids()
    print("  archive identifiers: %d" % len(arch))
    print()

    S, A = set(snap), set(arch)
    inter = S & A
    only_snap = S - A
    only_arch = A - S

    print("SET COMPARISON")
    print("=" * 70)
    print("  snapshot identifiers            : %d" % len(S))
    print("  archive identifiers             : %d" % len(A))
    print("  in BOTH                         : %d" % len(inter))
    print("  snapshot only (absent from ours): %d   <-- the unmatched remainder" % len(only_snap))
    print("  archive only (not in snapshot)  : %d   <-- the claimed omissions" % len(only_arch))
    print()
    print("  coverage of archive set by snapshot: %.1f%%  (manuscript says 64.6%%)"
          % (100.0 * len(inter) / len(A)))
    print("  implied coverage of snapshot by archive: %.1f%%"
          % (100.0 * len(inter) / len(S)))
    print()

    # theme composition of the two differences
    def theme_of(i):
        th = arch.get(i)
        if not th:
            return "?"
        return "/".join(sorted(th))

    print("THEME COMPOSITION")
    print("=" * 70)
    oa = Counter(theme_of(i) for i in only_arch)
    ins = Counter(theme_of(i) for i in inter)
    print("  omitted identifiers by theme (top 10):")
    tot_om = sum(oa.values()) or 1
    for th, n in oa.most_common(10):
        print("    %-30s %5d  (%.1f%% of omitted)" % (th, n, 100 * n / tot_om))
    veh_om = sum(n for th, n in oa.items() if "Vehicle" in th)
    veh_in = sum(n for th, n in ins.items() if "Vehicle" in th)
    print()
    print("  vehicle share of OMITTED : %.1f%%  (manuscript says 63.5%%)"
          % (100 * veh_om / tot_om))
    print("  vehicle share of MATCHED : %.1f%%  <-- the conditioned base rate"
          % (100 * veh_in / (sum(ins.values()) or 1)))
    print()

    if only_snap:
        print("SNAPSHOT-ONLY IDENTIFIERS (first 20):")
        for i in sorted(only_snap)[:20]:
            print("    %s" % i)
        print("  ... total %d" % len(only_snap))
        print()
        print("  These are the identifiers that should have been")
        print("  reconciled. If they are absent from our census, either our")
        print("  parsing misses them or the snapshot holds stale/extra rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
