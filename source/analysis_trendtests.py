#!/usr/bin/env python3
"""Round 13b: correctly sized trend tests, and the rarefied-Gini robustness check.

The paper's headline interval uses Newey--West with a t(12) critical value. That
test is oversized at fourteen points: simulated on pure noise it rejects about
15% of the time at a nominal 5% (21% with AR(1) rho=0.3), because the HAC
autocovariance sums with Bartlett weights can fall below the OLS variance and the
t(12) reference distribution ignores the estimation of the long-run variance.
With fourteen points the honest tests are OLS, a permutation test and
Mann--Kendall; we report those as primary and the HAC family as sensitivity.

Writes: results_trendtests.json
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np
from scipy.spatial import ConvexHull, cKDTree
from scipy import stats

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from analysis_common import load_years, ols_hac, gini_fixed_grid  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
NSIM = 20000


def ids_of(d):
    return np.array([(v[0], v[1]) for v in d.values()], float)


def locs_of(d):
    return np.unique(np.round(ids_of(d), 1), axis=0)


def ce(P, area):
    nn = cKDTree(P).query(P, k=2)[0][:, 1]
    return float(np.mean(nn) / (1.0 / (2.0 * math.sqrt(len(P) / area))))


def tests(v, ys, rng, nsim=NSIM):
    """OLS, permutation and Mann-Kendall on a fourteen-point series."""
    ys = np.asarray(ys, float)
    v = np.asarray(v, float)
    n = len(v)
    X = np.column_stack([np.ones(n), ys])
    beta = np.linalg.lstsq(X, v, rcond=None)[0]
    resid = v - X @ beta
    dof = n - 2
    se = math.sqrt((resid ** 2).sum() / dof / ((ys - ys.mean()) ** 2).sum())
    t = beta[1] / se
    p_ols = float(2 * stats.t.sf(abs(t), dof))
    # permutation: shuffle values across years
    perm = np.empty(nsim)
    for i in range(nsim):
        vp = v[rng.permutation(n)]
        bp = np.linalg.lstsq(X, vp, rcond=None)[0]
        perm[i] = bp[1]
    p_perm = float((np.abs(perm) >= abs(beta[1])).mean())
    tau, p_mk = stats.kendalltau(ys, v)
    # HAC, for comparison only
    b2, se2, r2, _ = ols_hac(v, X, 2)
    tc = stats.t.ppf(0.975, dof)
    return {
        "slope": float(beta[1]), "ols_se": float(se), "ols_t": float(t),
        "ols_p": p_ols, "perm_p": p_perm,
        "mk_tau": float(tau), "mk_p": float(p_mk),
        "nw_se": float(se2[1]), "nw_ci": [float(b2[1] - tc * se2[1]),
                                          float(b2[1] + tc * se2[1])],
        "n": n,
    }


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    Y = np.array(years, float)
    allP = np.vstack([ids_of(yrs[y]) for y in years])
    A = ConvexHull(allP).volume
    rng = np.random.default_rng(20261003)
    res = {"years": years, "A_hull_m2": float(A), "nsim": NSIM}

    Rh = np.array([ce(locs_of(yrs[y]), A) for y in years])
    Ri = np.array([ce(ids_of(yrs[y]), A) for y in years])
    boxL = np.array([ce(locs_of(yrs[y]), float((locs_of(yrs[y])[:, 0].max() - locs_of(yrs[y])[:, 0].min())
                                               * (locs_of(yrs[y])[:, 1].max() - locs_of(yrs[y])[:, 1].min())))
                     for y in years])

    print("\n[A] correctly sized trend tests on the fixed hull")
    res["hull_loc"] = tests(Rh, Y, rng)
    res["hull_ids"] = tests(Ri, Y, rng)
    keep = np.array([y != 2026 for y in years])
    res["hull_loc_no2026"] = tests(Rh[keep], Y[keep], rng)
    keep2 = np.array([y not in (2017, 2018, 2026) for y in years])
    res["hull_loc_no_disc"] = tests(Rh[keep2], Y[keep2], rng)
    for k in ("hull_loc", "hull_ids", "hull_loc_no2026", "hull_loc_no_disc"):
        d = res[k]
        print("  %-20s slope %+.4f | OLS p %.3f | perm p %.3f | MK p %.3f | NW CI [%+.4f,%+.4f]"
              % (k, d["slope"], d["ols_p"], d["perm_p"], d["mk_p"], d["nw_ci"][0], d["nw_ci"][1]))

    # ---- simulated size of the NW test ----
    print("\n[B] empirical size of the Newey--West t-test, nominal 5%")
    x = np.column_stack([np.ones(14), Y])
    tc = stats.t.ppf(0.975, 12)
    nsim_size = 6000
    sim = {}
    for rho in (0.0, 0.15, 0.3, 0.5):
        nw = ols = 0
        for _ in range(nsim_size):
            # e[0] is DRAWN, not zeroed. Starting the recursion at a
            # hard-zero first error is not a stationary AR(1) draw: it
            # shrinks the residual variance and makes the OLS test reject
            # well below its nominal size, which is an artefact of the
            # simulation and not a property of the test.
            e = np.zeros(14)
            e[0] = rng.normal()
            for t in range(1, 14):
                e[t] = rho * e[t - 1] + rng.normal()
            b, se, _, _ = ols_hac(e, x, 2)
            if abs(b[1] / se[1]) > tc:
                nw += 1
            bt = np.linalg.lstsq(x, e, rcond=None)[0]
            rt = e - x @ bt
            so = math.sqrt((rt ** 2).sum() / 12 / ((Y - Y.mean()) ** 2).sum())
            if abs(bt[1] / so) > tc:
                ols += 1
        sim["rho_%g" % rho] = {"nw_reject": nw / nsim_size,
                                 "ols_reject": ols / nsim_size}
        print("  rho=%.2f  NW rejects %.3f  |  OLS rejects %.3f"
              % (rho, nw / nsim_size, ols / nsim_size))
    res["size_nsim"] = nsim_size
    # Direct check that the OLS test is exact under i.i.d. Gaussian errors:
    # the size-sim design is an AR(1) recursion, so run a plain i.i.d. draw
    # as well rather than inferring the answer from rho=0 of the recursion.
    ols_iid = 0
    for _ in range(nsim_size):
        e = rng.normal(size=14)
        bt = np.linalg.lstsq(x, e, rcond=None)[0]
        rt = e - x @ bt
        so = math.sqrt((rt ** 2).sum() / 12 / ((Y - Y.mean()) ** 2).sum())
        if abs(bt[1] / so) > tc:
            ols_iid += 1
    sim["iid"] = {"ols_reject": ols_iid / nsim_size, "nw_reject": None}
    print("  iid      NW  n/a      |  OLS rejects %.3f (exact by construction)"
          % (ols_iid / nsim_size))
    res["size_sim"] = sim

    # ---- rarefied Gini robustness ----
    print("\n[C] rarefied Gini: is the residual decline robust?")
    g = json.loads((HERE / "results_gini.json").read_text())
    rows = g["res"]["20"]["rows"]
    rare = np.array([r["rare"] for r in rows])
    res["gini_rare_full"] = tests(rare, Y, rng)
    res["gini_rare_no2013"] = tests(rare[1:], Y[1:], rng)
    res["gini_rare_no2013_2026"] = tests(rare[1:-1], Y[1:-1], rng)
    for k in ("gini_rare_full", "gini_rare_no2013", "gini_rare_no2013_2026"):
        d = res[k]
        print("  %-24s slope %+.4f | OLS p %.3f | perm p %.3f | MK p %.3f | NW CI [%+.4f,%+.4f]"
              % (k, d["slope"], d["ols_p"], d["perm_p"], d["mk_p"], d["nw_ci"][0], d["nw_ci"][1]))

    # ---- infill: how many pairs are ABOVE the envelope ----
    print("\n[D] infill: observed median against the permutation envelope")
    d7 = json.loads((HERE / "results_rarefied.json").read_text())
    ir = d7["R7.6_random_labelling"]["rows"]
    above = [r["year"] for r in ir if r["obs_median_m"] > r["env_hi"]]
    inside = [r["year"] for r in ir if r["env_lo"] <= r["obs_median_m"] <= r["env_hi"]]
    below = [r["year"] for r in ir if r["obs_median_m"] < r["env_lo"]]
    res["infill"] = {"n": len(ir), "n_above": len(above), "n_inside": len(inside),
                     "n_below": len(below), "above": above, "inside": inside,
                     "below": below}
    print("  ABOVE the envelope: %d of %d -> %s" % (len(above), len(ir), above))
    print("  INSIDE             : %d -> %s  (2016 is INSIDE, so 13/13 is wrong)"
          % (len(inside), inside))
    print("  BELOW              : %d" % len(below))

    json.dump(res, open(HERE / "results_trendtests.json", "w"), indent=1)
    print("\nwrote results_trendtests.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
