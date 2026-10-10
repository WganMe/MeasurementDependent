"""Is the co-location an artefact of published coordinate precision?

Two coordinate-precision regimes exist in the archive, and the low-precision mode
has a resolution of ~0.11 m. If co-location is a registration/re-encoding effect,
it should be concentrated in the low-precision class, and the Clark-Evans fall
should shrink when only high-precision coordinates are used.
"""
import json, math
import numpy as np
from scipy.spatial import cKDTree

from analysis_common import load_years, bbox
from analysis_multiscale import ids_of, hull_edges

HERE = __import__("pathlib").Path(__file__).parent
HULL_A = json.loads((HERE / "results_tolerance.json").read_text())["hull_area_m2"]

DP_LOW, DP_HIGH = 6, 12


def dp_of(lon, lat):
    out = []
    for c in (lon, lat):
        s = repr(float(c))
        out.append(len(s.split(".")[1].rstrip("0")) if "." in s else 0)
    return min(out)                      # coarser of the two axes


def ce_r(P, area=HULL_A):
    n = len(P)
    if n < 5:
        return float("nan")
    nn = cKDTree(P).query(P, k=2)[0][:, 1]
    return float(np.mean(nn) / (1.0 / (2.0 * math.sqrt(n / area))))


def frac_within(P, r):
    nn = cKDTree(P).query(P, k=2)[0][:, 1]
    return float(np.mean(nn < r))


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    years = sorted(int(y) for y in idx["years"])

    # precision class per identifier-year record, pooled
    cls = {y: {"low": [], "high": [], "other": []} for y in years}
    lonlat_all = []
    for y in years:
        for i, v in idx["years"][str(y)]["identifiers"].items():
            if v[0] is None or v[1] is None:
                continue
            d = dp_of(v[0], v[1])
            lonlat_all.append(d)
            k = "low" if d <= DP_LOW else ("high" if d >= DP_HIGH else "other")
            cls[y][k].append((v[0], v[1]))
    a = np.array(lonlat_all)
    print("=" * 76)
    print("[1] TWO PUBLISHING PRECISION REGIMES")
    print("=" * 76)
    n = len(a)
    print("  records: %d" % n)
    print("  low  (<=%d dp, ~0.11 m resolution): %5d  (%.1f%%)"
          % (DP_LOW, (a <= DP_LOW).sum(), 100 * (a <= DP_LOW).mean()))
    print("  high (>=%d dp, sub-mm)           : %5d  (%.1f%%)"
          % (DP_HIGH, (a >= DP_HIGH).sum(), 100 * (a >= DP_HIGH).mean()))
    print("  other                            : %5d  (%.1f%%)"
          % (((a > DP_LOW) & (a < DP_HIGH)).sum(),
             100 * ((a > DP_LOW) & (a < DP_HIGH)).mean()))

    # --- 2. is co-location concentrated in the low-precision class? ---
    print()
    print("=" * 76)
    print("[2] CO-LOCATION BY PRECISION CLASS")
    print("=" * 76)
    res = {"n_records": int(n), "hull_area_m2": float(HULL_A), "by_year": {}}
    print("  %-6s %28s %28s" % ("year", "low precision", "high precision"))
    print("  %-6s %7s %11s %8s %7s %11s %8s"
          % ("", "n", "frac<25m", "frac<0.5m", "n", "frac<25m", "frac<0.5m"))
    for y in years:
        row = {}
        for k, label in (("low", "low"), ("high", "high")):
            arr = cls[y][k]
            if len(arr) < 5:
                row[label] = None
                continue
            from analysis_common import proj
            P = np.array([proj(lo, la) for lo, la in arr], float)
            row[label] = {"n": len(P),
                          "f25": frac_within(P, 25.0),
                          "f05": frac_within(P, 0.5)}
        res["by_year"][y] = row
        lo, hi = row.get("low"), row.get("high")
        print("  %-6d %7s %10s %8s %7s %10s %8s" % (
            y,
            lo["n"] if lo else "-", "%.3f" % lo["f25"] if lo else "-",
            "%.3f" % lo["f05"] if lo else "-",
            hi["n"] if hi else "-", "%.3f" % hi["f25"] if hi else "-",
            "%.3f" % hi["f05"] if hi else "-"))

    # --- 3. is the class difference the published precision itself? ---
    # Round the high-precision class to the low-precision quantum. If the two
    # classes then coincide alike, the difference between them is the encoding.
    print()
    print("=" * 76)
    print("[3] ROUNDING THE HIGH-PRECISION CLASS TO THE LOW-PRECISION QUANTUM")
    print("=" * 76)
    print("  %-6s %14s %14s %14s" % ("year", "high exact", "high ->6dp",
                                      "low exact"))
    from analysis_common import proj
    QUANT = 10 ** -6                      # ~0.111 m in latitude
    r3 = {}
    for y in years:
        e = idx["years"][str(y)]["identifiers"]
        hi_ll = [v for v in e.values() if v[0] is not None and v[1] is not None
                 and dp_of(v[0], v[1]) >= DP_HIGH]
        lo_ll = [v for v in e.values() if v[0] is not None and v[1] is not None
                 and dp_of(v[0], v[1]) <= DP_LOW]
        def sub_frac(arr, q=None):
            if len(arr) < 5:
                return None, len(arr)
            A = np.array([proj(v[0], v[1]) for v in arr], float)
            if q is not None:
                A = np.round(A / q) * q
            nnu = len(np.unique(np.round(A, 6), axis=0))
            return 100 * (1 - nnu / len(A)), len(A)
        f_hi, n_hi = sub_frac(hi_ll)
        f_hi_q, _ = sub_frac(hi_ll, QUANT)
        f_lo, n_lo = sub_frac(lo_ll)
        r3[y] = {"n_high": n_hi, "high_exact_collapse": f_hi,
                 "high_rounded_collapse": f_hi_q, "n_low": n_lo,
                 "low_exact_collapse": f_lo}
        fmt = lambda v: "-" if v is None else "%.1f%%" % v
        print("  %-6d %14s %14s %14s" % (y, fmt(f_hi), fmt(f_hi_q), fmt(f_lo)))
    res["rounding"] = {str(k): v for k, v in r3.items()}

    # --- 4. does the CE fall survive inside a single precision class? ---
    print()
    print("=" * 76)
    print("[4] CLARK-EVANS INSIDE ONE PRECISION CLASS (years that have it)")
    print("=" * 76)
    hp, allc = {}, {}
    for y in years:
        e = idx["years"][str(y)]["identifiers"]
        hi = [v for v in e.values() if v[0] is not None and v[1] is not None
              and dp_of(v[0], v[1]) >= DP_HIGH]
        al = [v for v in e.values() if v[0] is not None and v[1] is not None
              and abs(proj(v[0], v[1])[0]) < 60_000
              and abs(proj(v[0], v[1])[1]) < 60_000]
        hp[y] = np.array([proj(v[0], v[1]) for v in hi], float)
        allc[y] = np.array([proj(v[0], v[1]) for v in al], float)

    have = [y for y in years if len(hp[y]) >= 20]
    print("  years with >=20 high-precision records: %s" % have)
    Nmin = min(len(hp[y]) for y in have)
    print("  common N in that window: %d" % Nmin)

    full = np.array([ce_r(allc[y]) for y in years])
    print("  all records, full window    : R %.3f -> %.3f  fall %.1f%%"
          % (full[0], full[-1], 100 * (1 - full[-1] / full[0])))

    rng = np.random.default_rng(20261001)
    B = 200

    def matched(vals):
        obs = 100 * (1 - vals[-1] / vals[0])
        ctrl = np.empty(B)
        for b in range(B):
            yv = []
            for y in have:
                A = allc[y]
                yv.append(ce_r(A[rng.choice(len(A), Nmin, replace=False)]))
            yv = np.array(yv)
            ctrl[b] = 100 * (1 - yv[-1] / yv[0])
        return obs, ctrl

    hpr = np.array([ce_r(hp[y]) for y in have])
    obs_h, ctrl_h = matched(hpr)
    print()
    print("  high-precision class only, %d-%d:" % (have[0], have[-1]))
    print("    R %.3f -> %.3f, fall %.1f%%" % (hpr[0], hpr[-1], obs_h))
    print("    size-matched random control (N=%d, %d draws): %.1f%% [%.1f, %.1f]"
          % (Nmin, B, ctrl_h.mean(), np.percentile(ctrl_h, 2.5),
             np.percentile(ctrl_h, 97.5)))
    pctl = 100 * (ctrl_h < obs_h).mean()
    print("    -> percentile of the matched control: %.0f%%" % pctl)
    res["high_precision"] = {
        "years": have, "N_common": int(Nmin),
        "R_first": float(hpr[0]), "R_last": float(hpr[-1]),
        "fall_pct": float(obs_h),
        "control_mean": float(ctrl_h.mean()),
        "control_lo": float(np.percentile(ctrl_h, 2.5)),
        "control_hi": float(np.percentile(ctrl_h, 97.5)),
        "percentile": float(pctl),
        "all_fall_pct": float(100 * (1 - full[-1] / full[0]))}
    (HERE / "results_precision.json").write_text(json.dumps(res, indent=1))
    print("\nwrote results_precision.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
