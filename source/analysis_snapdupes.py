#!/usr/bin/env python3
"""Round 15c: the snapshot's 179 'absent' identifiers, resolved by location.

The audit reports 179 snapshot identifiers absent from the census, which reads as 179
missing instruments. But the census's own units are deduplicated locations, and the
paper's central finding is that the same place is registered under several
identifiers. So the right question is whether these 179 are missing INSTRUMENTS or
additional REGISTRATIONS at places the census already holds.

Writes: results_snapdupes.json
"""
import json, os, pathlib, sqlite3, sys
import numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from analysis_common import load_years, proj
from analysis_multiscale import locs_of

HERE = pathlib.Path(__file__).resolve().parent
# Committed benchmark snapshot (1,411 sensors; 2026-05-11 .. 2026-05-18).
# Override with UO_DB to use another copy.
DB = pathlib.Path(os.environ.get("UO_DB") or (HERE / "urban_observatory.db"))

idx = json.loads((HERE / "uo_archive_index.json").read_text())
yrs = load_years(idx); years = sorted(yrs)
census = set().union(*[set(yrs[y]) for y in years])

con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
snap = {}
for r in con.execute("SELECT raw_id, centroid_lon, centroid_lat FROM sensors"):
    snap[str(r["raw_id"]).strip()] = (r["centroid_lon"], r["centroid_lat"])
read_ids = {str(r[0]).strip() for r in
            con.execute("SELECT DISTINCT sensor_name FROM readings")}
con.close()

only_snap = [i for i in snap if i not in census and snap[i][0] is not None]
P = np.array([proj(*snap[i]) for i in only_snap])
C = np.vstack([locs_of(yrs[y]) for y in years])
C = np.unique(C, axis=0)
d, j = cKDTree(C).query(P, k=1)

res = {"n_snapshot_only": len(only_snap)}
for thr in (1, 5, 10, 25, 50):
    res["within_%dm" % thr] = int((d < thr).sum())
print("179 snapshot-only identifiers, distance to the nearest census LOCATION:")
for thr, lab in ((1, "within 1 m"), (5, "within 5 m"), (10, "within 10 m"),
                 (25, "within 25 m"), (50, "within 50 m")):
    n = int((d < thr).sum())
    print("  %-14s : %3d  (%4.1f%%)" % (lab, n, 100 * n / len(d)))
far = int((d >= 50).sum())
print("  beyond 50 m    : %3d" % far)
print("  median distance: %.1f m" % np.median(d))
res["median_dist_m"] = float(np.median(d))
res["beyond_50m"] = far

# how many distinct census locations do they land on?
print("  distinct census locations they fall on: %d" % len(set(j)))
res["distinct_locations"] = int(len(set(j)))

# the 24 with readings
rd = [i for i in read_ids if i in snap and snap[i][0] is not None and str(snap[i][0]) != "None"]
rd = [i for i in rd if snap[i][1] is not None]
if rd:
    Rd = np.array([proj(float(snap[i][0]), float(snap[i][1])) for i in rd])
    dd = cKDTree(C).query(Rd, k=1)[0]
else:
    Rd = np.zeros((0, 2)); dd = np.zeros(0)
print("\nthe %d identifiers that carry readings:" % len(rd))
print("  in the census        : %d" % sum(1 for i in rd if i in census))
print("  within 10 m of a census location: %d of %d" % (int((dd < 10).sum()), len(rd)))
print("  median distance to a census location: %.1f m" % np.median(dd))
res["reading_ids"] = {"n": len(rd), "in_census": sum(1 for i in rd if i in census),
                      "within_10m": int((dd < 10).sum()),
                      "median_dist_m": float(np.median(dd))}

json.dump(res, open(HERE / "results_snapdupes.json", "w"), indent=1)
print("\nwrote results_snapdupes.json")
