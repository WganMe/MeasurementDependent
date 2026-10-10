#!/usr/bin/env python3
"""The reframed analyses: is the apparent clustering trend measurement or geography?

WHY THIS EXISTS. Three things in the paper are currently wrong or untested.

(1) THE L THINNING TEST WAS SUPPORT-MISMATCHED. The published version thins the 2026
    pattern to 39 points drawn from the WHOLE hull and compares that envelope with 2013,
    whose 39 points occupy roughly a quarter of the hull. Thinning at large window and
    thinning at small window are different experiments, so the comparison conflated
    "more clustered at scale" with "occupies a smaller sub-region". Two corrected
    comparisons are run here:
      (a) support-matched window: every year's L recomputed on that year's OWN convex
          hull, so the density denominator matches the pattern's extent;
      (b) footprint-matched thinning: 2026 points inside that year's footprint are
          thinned to that year's count on that same window, which is the experiment the
          claim actually needs.

(2) THE DECOMPOSITION IS THE CLEANEST QUANTITATIVE RESULT AND WAS NEVER DONE PROPERLY.
        ln R = ln 2 + ln dbar + (1/2) ln N - (1/2) ln A
    so the apparent trend in R is the sum of a density term, a count term and a window
    term. Fitting ln dbar ~ ln N gives the exponent beta; beta = -1/2 is what pure
    densification forces, and random thinning must reproduce exactly -1/2. The distance
    of the observed beta from -1/2 is the only quantity that separates real clustering
    change from the arithmetic of a growing network.

(3) ISOTROPY. The paper frames itself on symmetry but never tests any. A directional
    K by orientation sector, against a CSR envelope in the same (itself anisotropic)
    hull, is the smallest analysis that makes the framing real rather than lexical.

Writes: results_reframe.json

Usage: python3 analysis_reframe.py
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np
from scipy.spatial import cKDTree
from scipy.stats import t as tdist, chi2

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from analysis_common import load_years, ce_r                       # noqa: E402
from analysis_multiscale import (                                  # noqa: E402
    RS, L_border, hull_edges, inward_lines, eroded_contains, ids_of, locs_of,
    sample_hull,
)
from analysis_tolerance import labels_single, reps_first           # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
SEED = 20261013
NDRAW = 299
NSEC = 8              # orientation sectors for the isotropy test
RISO = 1000.0         # radius for the isotropy test
NENV = 99             # CSR draws for the isotropy envelope


def hac(Y, v, lag=2):
    """OLS slope with Newey-West (lag 2) standard error."""
    n = len(Y)
    X = np.column_stack([np.ones(n), Y - Y.mean()])
    b = np.linalg.lstsq(X, v, rcond=None)[0]
    r = v - X @ b
    XtXi = np.linalg.inv(X.T @ X)
    S = np.zeros((2, 2))
    for l in range(lag + 1):
        w = 1.0 - l / (lag + 1)
        for i in range(n - l):
            u = np.outer(X[i], X[i + l]) * r[i] * r[i + l]
            S += w * (u + (u.T if l else 0))
    V = XtXi @ S @ XtXi
    return float(b[1]), float(math.sqrt(max(V[1, 1], 0.0)))


def mean_nn(P):
    if len(P) < 2:
        return float("nan")
    return float(np.mean(cKDTree(P).query(P, k=2)[0][:, 1]))


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    allP = np.vstack([ids_of(yrs[y]) for y in years])
    poly, A_hull = hull_edges(allP)
    rng = np.random.default_rng(SEED)
    res: dict = {"seed": SEED, "A_hull_m2": float(A_hull), "rs": RS.tolist()}

    # ============================================== 0. THE SHAPE OF THE PROBLEM
    print("=" * 78)
    print("[0] HOW MUCH OF THE HULL DOES EACH YEAR OCCUPY?")
    print("=" * 78)
    ext = {}
    for y in years:
        P = locs_of(yrs[y])
        _, A_y = hull_edges(P)
        ext[y] = {"n": int(len(P)), "A_own_m2": float(A_y),
                  "frac_of_hull": float(A_y / A_hull)}
    for y in years:
        print("  %d  n=%3d  own hull %7.1f km2  = %.3f of the full-record hull"
              % (y, ext[y]["n"], ext[y]["A_own_m2"] / 1e6, ext[y]["frac_of_hull"]))
    res["extent"] = {str(k): v for k, v in ext.items()}
    print("\n  -> a year whose footprint is a fraction of the hull has its density measured")
    print("     against the whole hull, so its L and R are inflated by support mismatch.")

    # ================================================ 1. SUPPORT-MATCHED L AND R
    print("\n" + "=" * 78)
    print("[1] EVERY YEAR ON ITS OWN HULL (support matched)")
    print("=" * 78)
    ownL, ownR = {}, {}
    for y in years:
        P = locs_of(yrs[y])
        poly_y, A_y = hull_edges(P)
        lines_y = inward_lines(poly_y)
        ownL[y] = L_border(P, A_y, lines=lines_y)
        ownR[y] = ce_r(P, A_y)
    yv = np.array(years, float)
    a10 = int(np.where(RS == 1000)[0][0])
    Lseq = np.array([ownL[y][a10] for y in years])
    s_own, se_own = hac(yv, Lseq)
    s_hull, se_hull = hac(yv, np.array([L_border(locs_of(yrs[y]), A_hull,
                                                 lines=inward_lines(poly))[a10]
                                        for y in years]))
    print("  L at 1 km, own hull   : " + " ".join("%6.0f" % v for v in Lseq))
    print("  L at 1 km, full hull  : " + " ".join(
        "%6.0f" % L_border(locs_of(yrs[y]), A_hull, lines=inward_lines(poly))[a10]
        for y in years))
    print("  trend, own hull  : %+.1f m/yr (se %.1f)" % (s_own, se_own))
    print("  trend, full hull : %+.1f m/yr (se %.1f)" % (s_hull, se_hull))
    res["L_own_hull"] = {"seq_1km": Lseq.tolist(), "slope": s_own, "se": se_own,
                         "slope_full_hull": s_hull, "se_full_hull": se_hull}
    rown = np.array([ownR[y] for y in years])
    print("  R, own hull      : " + " ".join("%6.3f" % v for v in rown))
    print("  R, full hull     : " + " ".join(
        "%6.3f" % ce_r(locs_of(yrs[y]), A_hull) for y in years))
    res["R_own_hull"] = {"first": float(rown[0]), "last": float(rown[-1]),
                         "fall_pct": float(100 * (rown[0] - rown[-1]) / rown[0])}
    print("  -> own-hull R falls %.1f%%, against %.1f%% on the full hull"
          % (res["R_own_hull"]["fall_pct"],
             100 * (ce_r(locs_of(yrs[2013]), A_hull)
                    - ce_r(locs_of(yrs[2026]), A_hull))
             / ce_r(locs_of(yrs[2013]), A_hull)))

    # ============================== 2. FOOTPRINT-MATCHED THINNING (the fair test)
    print("\n" + "=" * 78)
    print("[2] FOOTPRINT-MATCHED THINNING: 2026 inside each year's own footprint")
    print("=" * 78)
    P26 = locs_of(yrs[2026])
    fp_rows = []
    for y in years:
        Py = locs_of(yrs[y])
        n_y = len(Py)
        poly_y, A_y = hull_edges(Py)
        lines_y = inward_lines(poly_y)
        # 2026 locations that fall inside this year's footprint
        inside = P26[eroded_contains(P26, lines_y, 0.0)]
        if len(inside) < n_y:
            fp_rows.append({"year": int(y), "n": int(n_y), "n_avail": int(len(inside)),
                            "tested": False})
            print("  %d n=%3d  not testable: only %d of 2026's locations fall inside "
                  "that footprint" % (y, n_y, len(inside)))
            continue
        obs = L_border(Py, A_y, lines=lines_y)
        env = np.empty((NDRAW, len(RS)))
        for j in range(NDRAW):
            env[j] = L_border(inside[rng.choice(len(inside), n_y, replace=False)],
                              A_y, lines=lines_y)
        lo = np.nanpercentile(env, 2.5, axis=0)
        hi = np.nanpercentile(env, 97.5, axis=0)
        above = obs > hi
        fp_rows.append({"year": int(y), "n": int(n_y), "n_avail": int(len(inside)),
                        "tested": True, "obs_1km": float(obs[a10]),
                        "env_lo_1km": float(lo[a10]), "env_hi_1km": float(hi[a10]),
                        "above_scales": int(above.sum()),
                        "scales": int(np.isfinite(obs).sum()),
                        "obs": [None if not np.isfinite(v) else float(v) for v in obs],
                        "env_lo": lo.tolist(), "env_hi": hi.tolist()})
        tag = "ABOVE" if obs[a10] > hi[a10] else (
            "below" if obs[a10] < lo[a10] else "INSIDE")
        print("  %d n=%3d (from %3d available)  L(1km) obs %+7.0f  env [%+7.0f,%+7.0f]  %s"
              % (y, n_y, len(inside), obs[a10], lo[a10], hi[a10], tag))
    res["footprint_thinning"] = fp_rows
    tested = [r for r in fp_rows if r["tested"]]
    n_ab = sum(1 for r in tested if r["above_scales"] >= r["scales"] - 1)
    print("\n  of %d testable years, %d lie above the footprint-matched envelope"
          % (len(tested), n_ab))
    if tested:
        r13 = [r for r in tested if r["year"] == 2013]
        if r13:
            print("  2013: obs %.0f m against a footprint-matched envelope of %.0f-%.0f m"
                  % (r13[0]["obs_1km"], r13[0]["env_lo_1km"], r13[0]["env_hi_1km"]))
            print("  -> this is the number the claim must rest on, not the whole-hull one.")
    res["footprint_testable"] = len(tested)
    res["footprint_above"] = n_ab

    # ================================================ 3. THE DECOMPOSITION
    print("\n" + "=" * 78)
    print("[3] DECOMPOSITION  ln R = ln 2 + ln dbar + (1/2) ln N - (1/2) ln A")
    print("=" * 78)
    N = np.array([len(locs_of(yrs[y])) for y in years], float)
    dbar = np.array([mean_nn(locs_of(yrs[y])) for y in years])
    R = np.array([ce_r(locs_of(yrs[y]), A_hull) for y in years])
    # identity check on the fixed hull
    lhs = np.log(R)
    rhs = math.log(2.0) + np.log(dbar) + 0.5 * np.log(N) - 0.5 * math.log(A_hull)
    print("  identity check, max |ln R - (ln2 + ln dbar + lnN/2 - lnA/2)| = %.2e"
          % np.max(np.abs(lhs - rhs)))
    res["identity_max_err"] = float(np.max(np.abs(lhs - rhs)))

    b_d, se_d = hac(np.log(N), np.log(dbar))
    beta = b_d
    tc = tdist.ppf(0.975, len(N) - 2)
    # HAC se already gives the slope se; interval on the slope
    print("  ln dbar ~ ln N :  beta = %+.4f  se %.4f  CI [%+.4f,%+.4f]"
          % (beta, se_d, beta - tc * se_d, beta + tc * se_d))
    print("  pure-densification value is -0.5000")
    t_half = (beta - (-0.5)) / se_d
    print("  difference from -1/2: %+.4f, t = %.2f, p = %.3f"
          % (beta + 0.5, t_half, 2 * tdist.sf(abs(t_half), len(N) - 2)))
    res["decomposition"] = {"beta": float(beta), "beta_se": float(se_d),
                            "beta_ci": [float(beta - tc * se_d),
                                        float(beta + tc * se_d)],
                            "t_vs_half": float(t_half),
                            "p_vs_half": float(2 * tdist.sf(abs(t_half), len(N) - 2))}

    # empirical null: random thinning must give exactly -1/2
    print("\n  empirical null -- thin the 2026 pattern to each year's N, within the full")
    print("  hull, and fit the same exponent:")
    ok = N <= len(P26)
    logN_ok = np.log(N[ok])
    nulls = []
    for rep in range(20):
        db = np.array([mean_nn(P26[rng.choice(len(P26), int(n), replace=False)])
                       for n in N[ok]])
        bb, ss = hac(logN_ok, np.log(db))
        nulls.append(bb)
    nulls = np.array(nulls)
    print("  beta under random thinning: mean %+.4f, sd %.4f, range [%+.4f,%+.4f]"
          % (nulls.mean(), nulls.std(ddof=1), nulls.min(), nulls.max()))
    print("  -> random thinning reproduces -1/2 by construction, so the observed")
    print("     %+.4f is %s than the densification value."
          % (beta, "steeper" if beta < -0.5 else "shallower"))
    res["thinning_null_beta"] = {"mean": float(nulls.mean()),
                                 "sd": float(nulls.std(ddof=1)),
                                 "n_rep": int(len(nulls))}

    # and the same decomposition on the merged unit
    print("\n  the same fit on the merged site unit (25 m):")
    for tol, tag in ((0.0, "exact"), (10.0, "site10"), (25.0, "site25")):
        Ns, ds = [], []
        for y in years:
            P = ids_of(yrs[y])
            Q = np.unique(np.round(P, 1), axis=0) if tol <= 0 else \
                reps_first(P, labels_single(P, tol))
            Ns.append(len(Q))
            ds.append(mean_nn(Q))
        Ns = np.array(Ns, float)
        bs, ss = hac(np.log(Ns), np.log(np.array(ds)))
        th = (bs + 0.5) / ss
        print("    %-7s beta = %+.4f (se %.4f), t vs -1/2 = %.2f, p = %.3f"
              % (tag, bs, ss, th, 2 * tdist.sf(abs(th), len(Ns) - 2)))
        res.setdefault("decomposition_by_unit", {})[tag] = {
            "beta": float(bs), "se": float(ss), "t_half": float(th),
            "p_half": float(2 * tdist.sf(abs(th), len(Ns) - 2))}

    # ================================================ 4. ISOTROPY
    print("\n" + "=" * 78)
    print("[4] ISOTROPY: directional K by orientation sector, %d sectors, r = %.0f m"
          % (NSEC, RISO))
    print("=" * 78)

    def sector_fracs(P, lines, r=RISO, nsec=NSEC):
        m = len(P)
        if m < 10:
            return None
        tree = cKDTree(P)
        inside = eroded_contains(P, lines, r)
        ang = []
        for idx in np.nonzero(inside)[0]:
            nb = tree.query_ball_point(P[idx], r)
            for j in nb:
                if j == idx:
                    continue
                d = P[j] - P[idx]
                ang.append(math.atan2(d[1], d[0]) % math.pi)  # undirected
        if len(ang) < 50:
            return None
        h, _ = np.histogram(ang, bins=nsec, range=(0, math.pi))
        return h

    obs26c = sector_fracs(locs_of(yrs[2026]), inward_lines(poly))
    env = []
    for _ in range(NENV):
        Q = sample_hull(len(locs_of(yrs[2026])), poly, rng)
        f = sector_fracs(Q, inward_lines(poly))
        if f is not None:
            env.append(f)
    env = np.array(env)
    if obs26c is not None and len(env) > 10:
        # work in COUNTS for the chi-square; in fractions for the envelope comparison
        obs26 = obs26c / obs26c.sum()
        envf = env / env.sum(axis=1, keepdims=True)
        lo = np.percentile(envf, 2.5, axis=0)
        hi = np.percentile(envf, 97.5, axis=0)
        print("  sector        " + " ".join("%7d" % k for k in range(NSEC)))
        print("  observed      " + " ".join("%7.3f" % v for v in obs26))
        print("  CSR envelope lo" + " ".join("%7.3f" % v for v in lo))
        print("  CSR envelope hi" + " ".join("%7.3f" % v for v in hi))
        outside = int(((obs26 < lo) | (obs26 > hi)).sum())
        ratio = float(obs26.max() / obs26.min())
        print("  anisotropy ratio (max/min sector) = %.3f; sectors outside the CSR "
              "envelope: %d of %d" % (ratio, outside, NSEC))
        # chi-square against uniform, on COUNTS
        tot = obs26c.sum()
        exp = np.full(NSEC, tot / NSEC, float)
        chi = float(((obs26c - exp) ** 2 / exp).sum())
        pc = float(chi2.sf(chi, NSEC - 1))
        print("  total pairs %d; chi-square vs uniform: %.2f on %d df, p = %.3g"
              % (tot, chi, NSEC - 1, pc))
        res["isotropy"] = {"observed": obs26.tolist(), "env_lo": lo.tolist(),
                           "env_hi": hi.tolist(), "outside": outside,
                           "ratio": ratio, "chi2": chi, "chi2_p": pc,
                           "n_pairs": int(tot), "n_env": int(len(env))}
    else:
        print("  not enough pairs for the isotropy test at this radius")

    (HERE / "results_reframe.json").write_text(json.dumps(res, indent=1))
    print("\nwrote results_reframe.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
