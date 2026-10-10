#!/usr/bin/env python3
"""Round 13d: the snapshot audit properly conditioned.

Two facts were never stated in the paper and both matter:

  * the snapshot bundle was created 2026-09-20;
  * its `readings` table covers a single week, 2026-05-11 to 2026-05-18.

A 1411-identifier snapshot that carries one week of readings cannot be expected to
cover a fourteen-year census, so a coverage percentage computed against the whole
record is not a finding. The comparison is redone against identifiers that were
ACTIVE IN THE SNAPSHOT'S OWN WINDOW, which is the only like-for-like base.

Writes: results_snapshot.json
"""
from __future__ import annotations

import json
import os
import pathlib
import sqlite3

import numpy as np
from scipy import stats

from analysis_common import load_years

HERE = pathlib.Path(__file__).resolve().parent
# Committed benchmark snapshot (1,411 sensors; 2026-05-11 .. 2026-05-18).
# Override with UO_DB to use another copy.
DB = pathlib.Path(os.environ.get("UO_DB") or (HERE / "urban_observatory.db"))


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)

    con = sqlite3.connect(DB)
    cur = con.cursor()
    snap = {str(r[0]).strip() for r in cur.execute("SELECT raw_id FROM sensors")}
    lo, hi = cur.execute("SELECT MIN(timestamp), MAX(timestamp) FROM readings").fetchone()
    nread = cur.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    withread = {str(r[0]).strip() for r in
                cur.execute("SELECT DISTINCT sensor_name FROM readings")}
    con.close()

    census = set().union(*[set(yrs[y]) for y in years])
    res = {"snapshot_creation_utc": "2026-09-20T04:21:36+00:00",
           "readings_window": [lo, hi], "readings_rows": nread,
           "snapshot_ids": len(snap), "snapshot_ids_with_readings": len(withread),
           "census_ids": len(census)}

    print("\n[A] the snapshot's own extent")
    print("  creation          : %s" % res["snapshot_creation_utc"])
    print("  readings window   : %s .. %s   (%d rows, one week)" % (lo, hi, nread))
    print("  identifiers in `sensors`      : %d" % len(snap))
    print("  of those, with any reading    : %d" % len(withread))
    print("  census identifiers (2013-2026): %d" % len(census))

    both = snap & census
    only_snap = snap - census
    only_census = census - snap
    res["matched"] = len(both); res["only_snapshot"] = len(only_snap)
    res["only_census"] = len(only_census)
    res["coverage_of_census"] = 100.0 * len(both) / len(census)
    print("\n[B] the comparison as the paper reported it")
    print("  matched %d | snapshot-only %d | census-only %d | coverage %.1f%%"
          % (len(both), len(only_snap), len(only_census), res["coverage_of_census"]))

    # ---- the conditioned comparison: the snapshot's own window ----
    # The snapshot carries May 2026 readings. Condition the census base on the
    # identifiers active in the year the snapshot was drawn.
    print("\n[C] conditioned on the snapshot's own window (identifiers active in 2026)")
    active26 = set(yrs[2026])
    base26 = census & active26
    matched26 = snap & active26
    omitted26 = active26 - snap
    res["n_active_2026_census"] = len(active26)
    res["n_active_2026_in_snapshot"] = len(matched26)
    res["n_active_2026_omitted"] = len(omitted26)
    res["coverage_active_2026"] = 100.0 * len(matched26) / len(active26)
    print("  census identifiers active in 2026 : %d" % len(active26))
    print("  of those in the snapshot          : %d" % len(matched26))
    print("  omitted                           : %d" % len(omitted26))
    print("  coverage conditioned on 2026      : %.1f%%  (vs %.1f%% unconditioned)"
          % (res["coverage_active_2026"], res["coverage_of_census"]))

    # ---- vehicle contrast, conditioned ----
    def theme_of(y):
        return {k: v[2] for k, v in yrs[y].items()}

    def veh(ids):
        out = {}
        for y in years:
            t = theme_of(y)
            for i in ids:
                if i in t:
                    out[i] = t[i]
        return out

    def isveh(tv):
        return str(tv).lower().startswith("veh")

    alltv = veh(census)
    veh_rate_all = np.mean([isveh(alltv.get(i, "")) for i in census])
    veh_rate_om = np.mean([isveh(alltv.get(i, "")) for i in omitted26])
    veh_rate_in = np.mean([isveh(alltv.get(i, "")) for i in matched26])
    res["vehicle"] = {"base_all": float(veh_rate_all),
                      "omitted_2026cond": float(veh_rate_om),
                      "matched_2026cond": float(veh_rate_in)}
    print("\n[D] vehicle share, 2026-conditioned")
    print("  base, all census        : %.1f%%" % (100 * veh_rate_all))
    print("  base, active 2026       : %.1f%%"
          % (100 * np.mean([isveh(alltv.get(i, "")) for i in active26])))
    print("  omitted (2026-cond)     : %.1f%%" % (100 * veh_rate_om))
    print("  matched (2026-cond)     : %.1f%%" % (100 * veh_rate_in))
    a = int(np.sum([isveh(alltv.get(i, "")) for i in omitted26]))
    b = len(omitted26) - a
    c = int(np.sum([isveh(alltv.get(i, "")) for i in matched26]))
    d = len(matched26) - c
    orr = (a * d) / (b * c) if b * c else float("inf")
    _, p = stats.fisher_exact([[a, b], [c, d]])
    res["vehicle"]["table"] = [[a, b], [c, d]]
    res["vehicle"]["odds_ratio"] = float(orr)
    res["vehicle"]["fisher_p"] = float(p)
    print("  2x2 [[om_veh, om_other],[in_veh, in_other]] = %s" % [[a, b], [c, d]])
    print("  odds ratio %.2f   Fisher p = %.3g" % (orr, p))

    json.dump(res, open(HERE / "results_snapshot.json", "w"), indent=1)
    print("\nwrote results_snapshot.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
