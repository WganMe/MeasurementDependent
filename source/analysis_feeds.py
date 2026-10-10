#!/usr/bin/env python3
"""Round 16: who is actually in the frozen snapshot, and who is not.

The board review asks three questions the provenance audit did not answer:

  * are the 24 identifiers that carry readings representative of the catalogue,
    in broker (theme proxy), position or era?
  * are the 179 snapshot-only identifiers systematically different in theme?
  * what does the replacement rate look like against an external reference?

The `sensors` table stores no theme column, so `broker_name` is used as the
publisher-side proxy for theme: it names the feed each instrument is ingested
from, which is what the archive's theme directories are built from.

KEY TRAP, encountered twice in this project: `readings.sensor_name` joins to
`sensors.sensor_name`, NOT to `sensors.raw_id`, while the census is keyed on
`raw_id`. Joining readings to raw_id silently yields an empty intersection and
makes it look as though none of the reading-bearing identifiers are in the
census. Both joins are computed below so the difference is visible in the output.

Writes: results_feeds.json
"""
from __future__ import annotations

import collections
import json
import os
import pathlib
import sqlite3

HERE = pathlib.Path(__file__).resolve().parent
# Committed benchmark snapshot (1,411 sensors; 2026-05-11 .. 2026-05-18).
# Override with UO_DB to use another copy.
DB = pathlib.Path(os.environ.get("UO_DB") or (HERE / "urban_observatory.db"))


def ranked(counter, n=None):
    """`Counter.most_common()` with a deterministic tie-break.

    `most_common` is a stable sort on the count alone, so entries with equal
    counts come out in whatever order the source set iterated in. Python
    randomises `str` hashing per process, so the committed JSON would differ
    byte-for-byte between runs. Rank by (count descending, name ascending).
    """
    items = sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))
    return items if n is None else items[:n]


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())["years"]
    census: set[str] = set()
    first_year: dict[str, int] = {}
    for y in sorted(idx):
        for i in idx[y]["identifiers"]:
            census.add(i)
            first_year.setdefault(i, int(y))

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [(str(r["raw_id"]).strip(), r["sensor_name"], r["broker_name"])
            for r in con.execute(
                "SELECT raw_id, sensor_name, broker_name FROM sensors")]
    read_names = {r[0] for r in con.execute(
        "SELECT DISTINCT sensor_name FROM readings")}
    n_readings = con.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    # `c DESC, variable` -- the second key makes equal counts deterministic, so
    # the committed JSON is byte-stable across SQLite versions and CI runs.
    var_counts = [(r[0], r[1]) for r in con.execute(
        "SELECT variable, COUNT(*) c FROM readings "
        "GROUP BY variable ORDER BY c DESC, variable ASC")]
    con.close()

    snap = {rid: (nm, bk) for rid, nm, bk in rows}
    res: dict = {
        "sensors_rows": len(snap),
        "census_ids": len(census),
        "readings_rows": n_readings,
        "readings_distinct_identifiers": len(read_names),
        "readings_variables": var_counts,
    }

    # ---- the join that matters -------------------------------------------
    # correct: readings.sensor_name -> sensors.sensor_name
    by_name = {nm: rid for rid, (nm, _) in snap.items()}
    reading_ids = {by_name[n] for n in read_names if n in by_name}
    # the wrong join, kept so the reader can see why the earlier probe said "0"
    wrong_join = {rid for rid in read_names if rid in snap}
    res["reading_bearing"] = {
        "n": len(reading_ids),
        "matched_via_sensor_name": len(reading_ids),
        "matched_via_raw_id_wrong_join": len(wrong_join),
        "in_census": len(reading_ids & census),
        "snapshot_only": len(reading_ids - census),
        "broker_mix": ranked(collections.Counter(snap[i][1] for i in reading_ids)),
    }

    matched = {rid for rid in snap if rid in census}
    only_snap = {rid for rid in snap if rid not in census}
    res["matched"] = len(matched)
    res["snapshot_only"] = len(only_snap)
    res["broker_mix_matched"] = ranked(
        collections.Counter(snap[i][1] for i in matched))
    res["broker_mix_snapshot_only"] = ranked(
        collections.Counter(snap[i][1] for i in only_snap))

    # ---- are the 24 representative of the catalogue's brokers? ------------
    # ---- feed concentration in each subset --------------------------------
    m = dict(res["broker_mix_matched"])
    sn = dict(res["broker_mix_snapshot_only"])
    res["largest_snapshot_only_feed"] = res["broker_mix_snapshot_only"][0][0]
    res["building_feeds"] = {
        "snapshot_only": sn.get("Internal Building Sensors", 0) + sn.get("Building External Sensor", 0),
        "matched": m.get("Internal Building Sensors", 0) + m.get("Building External Sensor", 0),
        "internal_only_matched": m.get("Internal Building Sensors", 0),
        "external_only_matched": m.get("Building External Sensor", 0),
    }

    total_brokers = collections.Counter(snap[i][1] for i in snap)
    top = [b for b, _ in ranked(total_brokers, 8)]
    res["representativeness"] = {
        "n_brokers_in_snapshot": len(total_brokers),
        "top_brokers": ranked(total_brokers, 8),
        "reading_bearing_brokers": len({snap[i][1] for i in reading_ids}),
        "reading_bearing_share_of_top8": sum(
            1 for i in reading_ids if snap[i][1] in top),
    }

    # ---- era: when did each identifier first appear in the archive? --------
    eras = collections.Counter()
    for i in only_snap:
        y = first_year.get(i)
        eras["absent from the archive" if y is None else str(y)] += 1
    res["snapshot_only_first_year"] = ranked(eras)
    res["snapshot_only_brokers_absent_from_archive"] = ranked(
        collections.Counter(snap[i][1] for i in only_snap if i not in first_year))

    # ---- how many brokers contribute snapshot-only identifiers -------------
    never = {snap[i][1] for i in only_snap if i not in first_year}
    res["brokers_contributing_snapshot_only"] = sorted(never)

    json.dump(res, open(HERE / "results_feeds.json", "w"), indent=1)

    print("== the join ==")
    print("  readings rows %d, distinct identifiers %d"
          % (n_readings, len(read_names)))
    print("  joined via sensor_name  : %d identifiers" % len(reading_ids))
    print("  joined via raw_id (wrong): %d identifiers  <-- the empty-intersection trap"
          % len(wrong_join))
    print("  of the reading-bearing identifiers, in the census: %d of %d"
          % (len(reading_ids & census), len(reading_ids)))
    print()
    print("== the 24 are not a cross-section ==")
    print("  brokers: %s" % (res["reading_bearing"]["broker_mix"],))
    print("  distinct brokers among them: %d of %d in the catalogue"
          % (res["representativeness"]["reading_bearing_brokers"],
             res["representativeness"]["n_brokers_in_snapshot"]))
    print("  readings variables: %s" % (var_counts[:6],))
    print()
    print("== broker mix, matched vs snapshot-only ==")
    print("  matched       : %s" % (res["broker_mix_matched"][:6],))
    print("  snapshot-only : %s" % (res["broker_mix_snapshot_only"][:6],))
    print()
    print("== when the snapshot-only identifiers were first seen ==")
    for k, v in res["snapshot_only_first_year"]:
        print("  %-26s %d" % (k, v))
    print("  brokers that contribute snapshot-only identifiers: %d"
          % len(res["brokers_contributing_snapshot_only"]))
    print()
    print("wrote results_feeds.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
