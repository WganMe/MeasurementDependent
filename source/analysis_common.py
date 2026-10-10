#!/usr/bin/env python3
"""
The core analyses. All read uo_archive_index.json, so this
runs in seconds rather than re-walking the archive.

 1. deduplicated-location census: N, R, and churn recomputed on unique locations
 2. R inside a defined core with an edge correction, and an inhomogeneous null
 3. multiscale Ripley K and L curves per year, with edge correction
 4. regression of ln R on ln N and year jointly, with HAC (Newey-West) errors
 5. sensitivity: exclude 2017-2018, and handle the partial 2026
 6. fixed-grid Gini (geographically fixed cells, so years are comparable)
 7. snapshot reconciliation and a base-rate test for the vehicle-omission claim

Usage:  python3 analysis_common.py [--index uo_archive_index.json]
                                   [--out results_core_legacy.json]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sqlite3
from collections import Counter, defaultdict

import numpy as np
from scipy.spatial import cKDTree

HERE = pathlib.Path(__file__).resolve().parent
LAT0, LON0, R_EARTH = 54.97, -1.61, 6371000.0
LIMIT_M = 60000.0
# The benchmark snapshot database, committed here so the analysis runs anywhere.
# It holds the 1,411-sensor catalogue and a one-week readings window
# (2026-05-11 .. 2026-05-18), the window the manuscript reports. Override with
# UO_DB to point at a different copy.
DB = pathlib.Path(os.environ.get("UO_DB") or (HERE / "urban_observatory.db"))


def proj(lon: float, lat: float) -> tuple[float, float]:
    x = math.radians(lon - LON0) * R_EARTH * math.cos(math.radians(LAT0))
    y = math.radians(lat - LAT0) * R_EARTH
    return x, y


def load_years(idx: dict) -> dict[int, dict[str, tuple[float, float, str, str]]]:
    """year -> {identifier: (x, y, theme/variable, first_date)} for in-range points."""
    out = {}
    for ys, d in idx["years"].items():
        pts = {}
        for i, (lon, lat, tv, ts) in d["identifiers"].items():
            if lon is None or lat is None:
                continue
            x, y = proj(lon, lat)
            if abs(x) < LIMIT_M and abs(y) < LIMIT_M:
                pts[i] = (x, y, tv, ts)
        out[int(ys)] = pts
    return out


# ---------------------------------------------------------------- statistics
def ce_r(P: np.ndarray, area: float) -> float:
    """Clark-Evans R for a given reference area (m^2)."""
    n = len(P)
    if n < 3 or area <= 0:
        return float("nan")
    nn = cKDTree(P).query(P, k=2)[0][:, 1]
    rho = n / area
    return float(np.mean(nn) / (1.0 / (2.0 * math.sqrt(rho))))


def bbox(P: np.ndarray) -> float:
    return float((P[:, 0].max() - P[:, 0].min()) * (P[:, 1].max() - P[:, 1].min()))


def donnelly_ce(P: np.ndarray, half_side: float) -> tuple[float, float]:
    """
    WITHDRAWN — kept only so that nothing silently reintroduces it.

    Donnelly (1978) corrects the mean nearest-neighbour distance for points near
    the boundary of a finite window. This implementation is wrong and must not be
    used or cited. Its correction term was

        corr = (2 d / pi) * arctan(2 d / nn)

    where d is the distance to the nearest edge. That term is not Donnelly's; it
    grows without bound as d increases, so points far from the edge receive the
    largest "correction" when the true correction there is smallest. On a pattern
    of known complete spatial randomness, where R is 1 by definition, it returns

        n=100 -> R = 4.47      n=500 -> R = 8.31      n=1000 -> R = 11.07

    and R keeps climbing with n (verify_estimators.py). The values it produced on
    the core are therefore meaningless and have been removed from the results.

    What the paper reports instead: R inside the 5-95% core is computed with the
    plain Clark-Evans estimator using the core's own rectangular area. That
    estimator recovers R ~ 1.00-1.05 on synthetic CSR patterns and is left
    unadjusted, so the paper declares it as uncorrected rather than claiming an
    edge correction it does not have.
    """
    raise NotImplementedError(
        "donnelly_ce is withdrawn: its correction is unbounded and returns R=4.5-16 "
        "on complete spatial randomness. Use ce_r with the core's own area."
    )


def ripley_kl(P: np.ndarray, half_side: float, r_max: float,
              n_r: int = 40) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Ripley's K on a square window with the translational edge correction, and
    L(r) = sqrt(K/pi) - r, so L = 0 under CSR.
    """
    n = len(P)
    if n < 5:
        return np.array([]), np.array([]), np.array([])
    rs = np.linspace(r_max / n_r, r_max, n_r)
    cx = half_side
    tree = cKDTree(P)
    pairs = tree.query_pairs(r_max, output_type="ndarray")
    if len(pairs) == 0:
        return rs, np.zeros_like(rs), np.zeros_like(rs)
    d = np.linalg.norm(P[pairs[:, 0]] - P[pairs[:, 1]], axis=1)

    # Standard TRANSLATIONAL edge correction (Ripley 1977; Diggle 1983).
    # For a rectangular window of sides a and b, a pair separated by (dx, dy)
    # is weighted by w = (a - dx)(b - dy) / (a b), the fraction of the shifted
    # window that still overlaps the original. The weight reaches zero only when
    # the separation equals the FULL side length.
    #
    # This replaces an earlier weight, (half - dx)(half - dy)/half^2 with
    # half = side/2, which decayed twice as fast and reached zero at HALF the
    # side. That version under-counted pairs in the outer part of the window and
    # biased L downward: on a known complete-spatial-randomness pattern it
    # returned L around -250 m where the answer is 0 (verify_ripley_sign.py).
    def weight(dd: np.ndarray) -> np.ndarray:
        out = np.zeros_like(dd)
        for k, (i, j) in enumerate(pairs):
            dx = abs(P[i, 0] - P[j, 0])
            dy = abs(P[i, 1] - P[j, 1])
            w_x = max(0.0, 2.0 * cx - dx) / (2.0 * cx)
            w_y = max(0.0, 2.0 * cx - dy) / (2.0 * cx)
            out[k] = w_x * w_y
        return out

    w = weight(d)
    area = (2 * cx) ** 2
    lam = n / area
    K = np.empty_like(rs)
    for m, r in enumerate(rs):
        sel = d <= r
        if not np.any(sel):
            K[m] = 0.0
            continue
        # Ripley's estimator, Diggle (1983) form:
        #   K(r) = |W| / (n (n-1)) * sum_{i != j} I(d_ij <= r) / w_ij
        # The sum runs over ORDERED pairs i != j. cKDTree.query_pairs returns each
        # unordered pair {i, j} exactly once, so the sum over j < i must be doubled.
        # The earlier version omitted that factor of 2 and used n^2 rather than
        # n(n-1); K came out at half its true value, which drove L = sqrt(K/pi) - r
        # to about -0.293 r. On a known complete-spatial-randomness pattern it
        # returned L ~ -280 m where the exact answer is 0 (verify_ripley_sign.py).
        K[m] = (2.0 * area / (n * (n - 1))) * np.sum(1.0 / np.maximum(w[sel], 1e-6))
    L = np.sqrt(K / math.pi) - rs
    return rs, K, L


def gini_fixed_grid(P: np.ndarray, origin: tuple[float, float],
                    cell: float, nx: int = 20) -> float:
    """Gini over occupied cells of a grid FIXED in geographic space."""
    if len(P) < 3:
        return float("nan")
    ix = np.floor((P[:, 0] - origin[0]) / cell).astype(int)
    iy = np.floor((P[:, 1] - origin[1]) / cell).astype(int)
    keep = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < nx)
    if keep.sum() < 3:
        return float("nan")
    counts = np.array(list(Counter(zip(ix[keep], iy[keep])).values()), float)
    counts.sort()
    n = len(counts)
    tot = counts.sum()
    idx = np.arange(1, n + 1)
    return float((2.0 * np.sum(idx * counts) / (n * tot)) - (n + 1.0) / n)


def ols_hac(y: np.ndarray, X: np.ndarray, lag: int = 2):
    """OLS with Newey-West HAC standard errors. X must include a constant column."""
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    resid = y - X @ beta
    n, k = X.shape
    S = np.zeros((k, k))
    for t in range(n):
        xt = X[t][:, None]
        S += (resid[t] ** 2) * (xt @ xt.T)
    for l in range(1, lag + 1):
        w = 1.0 - l / (lag + 1.0)
        for t in range(l, n):
            xt = X[t][:, None]
            xtl = X[t - l][:, None]
            G = resid[t] * resid[t - l] * (xt @ xtl.T)
            S += w * (G + G.T)
    cov = XtX_inv @ S @ XtX_inv
    se = np.sqrt(np.diag(cov))
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1.0 - np.sum(resid ** 2) / ss_tot if ss_tot > 0 else float("nan")
    return beta, se, r2, resid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default=str(HERE / "uo_archive_index.json"))
    ap.add_argument("--out", default=str(HERE / "results_core_legacy.json"))
    a = ap.parse_args()

    idx = json.loads(pathlib.Path(a.index).read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    res: dict = {"years": years}
    print("loaded index: %s" % idx["built"])
    print("total files : %s" % idx.get("total_files"))

    # ============================================================ ANALYSIS 1
    print("\n[1] deduplicated-location census")
    a1 = []
    for y in years:
        pts = yrs[y]
        P = np.array([(v[0], v[1]) for v in pts.values()], float)
        loc = {}
        for v in pts.values():
            loc.setdefault((round(v[0], 1), round(v[1], 1)), 1)
        Q = np.array(list(loc), float)
        a1.append({
            "year": y,
            "n_identifiers": len(P),
            "n_locations": len(Q),
            "dup_pct": 100.0 * (len(P) - len(Q)) / len(P) if len(P) else 0.0,
            "R_identifiers": ce_r(P, bbox(P)),
            "R_locations": ce_r(Q, bbox(Q)),
        })
        print("  %d ids=%-4d locs=%-4d dup=%4.1f%%  R_ids=%.3f R_locs=%.3f"
              % (y, len(P), len(Q), a1[-1]["dup_pct"],
                 a1[-1]["R_identifiers"], a1[-1]["R_locations"]))
    res["A1_dedup"] = a1

    # churn at location level and identifier level
    print("\n[1b] churn: identifier vs location level")
    churn = []
    prev_ids = prev_locs = None
    for y in years:
        ids = set(yrs[y])
        locs = {(round(v[0], 1), round(v[1], 1)) for v in yrs[y].values()}
        if prev_ids is not None:
            churn.append({
                "year": y,
                "loc_births": len(locs - prev_locs),
                "loc_deaths": len(prev_locs - locs),
                "id_births": len(ids - prev_ids),
                "id_deaths": len(prev_ids - ids),
            })
            print("  %d loc +/- %-4d/%-4d   id +/- %-5d/%-5d"
                  % (y, churn[-1]["loc_births"], churn[-1]["loc_deaths"],
                     churn[-1]["id_births"], churn[-1]["id_deaths"]))
        prev_ids, prev_locs = ids, locs
    res["A1b_churn"] = churn

    # ============================================================ ANALYSIS 2
    print("\n[2] R inside a defined core (rectangle, 5-95% per axis, own area)")
    a2 = []
    for y in years:
        P = np.array([(v[0], v[1]) for v in yrs[y].values()], float)
        if len(P) < 5:
            continue
        # Core definition must match census_model.py exactly, which is the source
        # of the footprint figures the manuscript reports (335 -> 528 km2). That
        # definition is the rectangle between the 5th and 95th percentile ON EACH
        # AXIS SEPARATELY, so it is asymmetric and retains 90% of points per axis.
        # An earlier version here used percentile(|x|, 95), which builds a
        # symmetric square, discards about 19% of the points, and gave
        # 716 -> 1255 km2 — a different quantity that then disagreed with the
        # manuscript. The rectangle is the one the paper describes.
        lo = np.percentile(P, 5, axis=0)
        hi = np.percentile(P, 95, axis=0)
        keep = ((P[:, 0] >= lo[0]) & (P[:, 0] <= hi[0]) &
                (P[:, 1] >= lo[1]) & (P[:, 1] <= hi[1]))
        C = P[keep]
        width = float(hi[0] - lo[0])
        height = float(hi[1] - lo[1])
        r_box = ce_r(C, width * height)
        a2.append({"year": y, "n_core": len(C),
                   "core_km2": width * height / 1e6,
                   "R_core_box": r_box})
        print("  %d n_core=%-4d core=%7.1f km2  R_box=%.3f"
              % (y, len(C), a2[-1]["core_km2"], r_box))
    res["A2_core"] = a2

    # inhomogeneous null: a smoothed bootstrap of the observed intensity.
    #
    # Three things the manuscript must state, and previously did not:
    #   - the bandwidth, in metres (see JITTER_M below, now derived from the data)
    #   - the unit, which is IDENTIFIERS to match the headline series. An earlier
    #     version built the null and the observation from deduplicated LOCATIONS,
    #     so the table compared a different quantity from every other R in the
    #     paper.
    #   - that the null is constructed from the same points it is used to test,
    #     so it is not independent evidence; it is a comparison against the
    #     pattern's own smoothed intensity.
    print("\n[2b] z-scores against a density-smoothed (inhomogeneous) null, identifiers")
    z_rows = []
    for rec in a1:
        y = rec["year"]
        P = np.array([(v[0], v[1]) for v in yrs[y].values()], float)
        if len(P) < 30:
            continue
        # Bandwidth: the median nearest-neighbour separation among DISTINCT
        # locations, so the smoothing is matched to the typical instrument
        # spacing and the null preserves the density field at all scales coarser
        # than that spacing.
        Q = np.unique(np.round(P, 1), axis=0)
        if len(Q) < 3:
            continue
        nn = cKDTree(Q).query(Q, k=2)[0][:, 1]
        bandwidth = float(np.median(nn))
        obs = rec["R_identifiers"]
        rng = np.random.default_rng(20260930)
        n = len(P)
        sims = []
        for _ in range(999):
            pick = rng.integers(0, len(Q), size=n)
            S = Q[pick] + rng.normal(0.0, bandwidth, size=(n, 2))
            sims.append(ce_r(S, bbox(S)))
        sims = np.array([s for s in sims if np.isfinite(s)])
        if len(sims) > 10:
            z = (obs - sims.mean()) / sims.std(ddof=1)
            z_rows.append({"year": y, "R": obs, "null_mean": float(sims.mean()),
                           "null_sd": float(sims.std(ddof=1)), "z": float(z),
                           "bandwidth_m": bandwidth, "n_perm": len(sims)})
            print("  %d bw=%5.1f m  R=%.3f  null=%.3f+-%.3f  z=%+.1f"
                  % (y, bandwidth, obs, sims.mean(), sims.std(ddof=1), z))
    res["A2b_z"] = z_rows

    # ============================================================ ANALYSIS 3
    print("\n[3] multiscale Ripley K and L (translational correction)")
    a3 = []
    for y in years:
        P = np.array([(v[0], v[1]) for v in yrs[y].values()], float)
        if len(P) < 20:
            continue
        half = 0.5 * max(P[:, 0].max() - P[:, 0].min(),
                         P[:, 1].max() - P[:, 1].min())
        rs, K, L = ripley_kl(P, half, r_max=min(2000.0, half))
        if len(rs) == 0:
            continue
        a3.append({"year": y, "r_m": rs.tolist(), "K": K.tolist(), "L": L.tolist(),
                   "L_min": float(L.min()), "r_at_Lmin_m": float(rs[int(np.argmin(L))])})
        print("  %d  L range %+.1f .. %+.1f m  (L>0 => clustering, L<0 => dispersion)"
              % (y, L.min(), L.max()))
    res["A3_kl"] = a3

    # ============================================================ ANALYSIS 4
    print("\n[4] ln R on ln N and year jointly, HAC standard errors")
    rows = [r for r in a1 if np.isfinite(r["R_identifiers"]) and r["n_identifiers"] > 0]
    lnR = np.array([math.log(r["R_identifiers"]) for r in rows])
    lnN = np.array([math.log(r["n_identifiers"]) for r in rows])
    yr = np.array([r["year"] for r in rows], float)
    ones = np.ones_like(lnN)

    def fit(cols, names, lag=2):
        X = np.column_stack(cols)
        beta, se, r2, _ = ols_hac(lnR, X, lag)
        out = {}
        for nm, b, s in zip(names, beta, se):
            out[nm] = {"coef": float(b), "hac_se": float(s),
                       "t": float(b / s) if s > 0 else float("nan")}
        out["r2"] = float(r2)
        return out

    f_n = fit([ones, lnN], ["const", "lnN"])
    f_t = fit([ones, yr], ["const", "year"])
    f_b = fit([ones, lnN, yr], ["const", "lnN", "year"])

    # --------------------------------------------------- 4a dependence-robust fit
    # Section 3.2 reports a bootstrap interval and a Mann-Kendall test that both
    # treat the fourteen annual values as independent. They are not: R is strongly
    # autocorrelated. A circular moving-block bootstrap over the yearly series, and
    # the Bartlett/Newey-West interval on the same slope, both respect that.
    Rv = np.array([r["R_identifiers"] for r in rows], float)
    Yr = np.array([r["year"] for r in rows], float)
    n_ = len(Rv)

    def ols_slope(y, x):
        X = np.column_stack([np.ones_like(x), x])
        b, *_ = np.linalg.lstsq(X, y, rcond=None)
        return b[1]

    obs_slope = ols_slope(Rv, Yr)
    b_se, se_se, _, _ = ols_hac(Rv, np.column_stack([ones, Yr]), 2)
    _, _, _, resid = ols_hac(Rv, np.column_stack([ones, Yr]), 2)

    # residual autocorrelation, to show the assumption actually fails
    ac1 = float(np.corrcoef(resid[:-1], resid[1:])[0, 1])

    # circular moving-block bootstrap, block length 3 (short series)
    rngb = np.random.default_rng(1234)
    blk = 3
    boot = []
    for _ in range(5000):
        bidx = []
        while len(bidx) < n_:
            s = rngb.integers(0, n_)
            bidx.extend([(s + k) % n_ for k in range(blk)])
        bidx = np.array(bidx[:n_])
        boot.append(ols_slope(Rv[bidx], Yr[bidx]))
    boot = np.array(boot)
    lo, hi = np.percentile(boot, [2.5, 97.5])

    res["A4a_dependence"] = {
        "slope_ols": float(obs_slope),
        "slope_hac_se": float(se_se[1]),
        "hac_ci95": [float(b_se[1] - 1.96 * se_se[1]), float(b_se[1] + 1.96 * se_se[1])],
        "block_bootstrap_ci95": [float(lo), float(hi)],
        "block_length": blk, "n_boot": int(len(boot)),
        "residual_lag1_autocorr": ac1,
    }
    print("  dependence-robust slope: OLS %+.4f  HAC se %.4f  CI95 [%+.4f, %+.4f]"
          % (obs_slope, se_se[1], b_se[1] - 1.96 * se_se[1], b_se[1] + 1.96 * se_se[1]))
    print("  circular block bootstrap CI95 (block=%d, 5000 draws): [%+.4f, %+.4f]"
          % (blk, lo, hi))
    print("  residual lag-1 autocorrelation = %+.3f" % ac1)

    res["A4_models"] = {"lnR_on_lnN": f_n, "lnR_on_year": f_t, "lnR_on_both": f_b}
    for nm, f in (("lnR~lnN", f_n), ("lnR~year", f_t), ("lnR~lnN+year", f_b)):
        terms = "  ".join("%s=%.4f(se %.4f)" % (k, v["coef"], v["hac_se"])
                          for k, v in f.items() if isinstance(v, dict))
        print("  %-14s R2=%.3f   %s" % (nm, f["r2"], terms))

    # ---------------------------------------------------------- 4b collinearity
    # How badly ln N and year are collinear, because two
    # near-collinear regressors make both sets of standard errors unreliable.
    # Report the Pearson correlation, its square, and the variance inflation
    # factor for each term (VIF = 1/(1-R^2_j) from the auxiliary regression of
    # one regressor on the other).
    r_ny = float(np.corrcoef(lnN, yr)[0, 1])
    A_aux = np.column_stack([ones, yr])
    b_aux, _, r2_aux, _ = ols_hac(lnN, A_aux, 0)
    vif = 1.0 / (1.0 - r2_aux) if r2_aux < 1 else float("inf")
    res["A4b_collinearity"] = {
        "corr_lnN_year": r_ny, "r2_aux": float(r2_aux), "vif": float(vif),
        "condition_number": float(np.linalg.cond(np.column_stack([ones, lnN, yr]))),
    }
    print("  collinearity: corr(lnN, year) = %+.4f   R2_aux = %.4f   VIF = %.2f"
          % (r_ny, r2_aux, vif))
    print("  condition number of the design = %.1f"
          % np.linalg.cond(np.column_stack([ones, lnN, yr])))

    # A second, model-free view: fit the slope on each predictor alone over every
    # contiguous 10-14 year window, which shows how much the attribution depends
    # on which years enter.
    win = []
    for start in range(0, len(rows) - 9):
        sub = rows[start:start + 10]
        L = np.log([r["R_identifiers"] for r in sub])
        N = np.log([r["n_identifiers"] for r in sub])
        Y = np.array([r["year"] for r in sub], float)
        bN = np.polyfit(N, L, 1)[0]
        bY = np.polyfit(Y, L, 1)[0]
        win.append({"start": sub[0]["year"], "end": sub[-1]["year"],
                    "slope_on_lnN": float(bN), "slope_on_year": float(bY)})
    res["A4c_windows"] = win
    print("  10-year windows: on lnN slope range [%.3f, %.3f], on year [%.3f, %.3f]"
          % (min(w["slope_on_lnN"] for w in win), max(w["slope_on_lnN"] for w in win),
             min(w["slope_on_year"] for w in win), max(w["slope_on_year"] for w in win)))

    # ============================================================ ANALYSIS 5
    print("\n[5] sensitivity: exclude 2017-2018; 2026 month coverage")
    def slope_over(sel):
        L = np.log([r["R_identifiers"] for r in rows if sel(r)])
        Y = np.array([r["year"] for r in rows if sel(r)], float)
        X = np.column_stack([np.ones_like(Y), Y])
        b, s, r2, _ = ols_hac(L, X, 2)
        return float(b[1]), float(s[1]), float(r2)

    a5 = {"all_years": slope_over(lambda r: True),
          "excl_2017_2018": slope_over(lambda r: r["year"] not in (2017, 2018)),
          "excl_2026": slope_over(lambda r: r["year"] != 2026),
          "excl_2017_2018_2026": slope_over(lambda r: r["year"] not in (2017, 2018, 2026))}
    for k, v in a5.items():
        print("  %-22s slope=%+.4f  HAC se %.4f  R2=%.3f" % (k, v[0], v[1], v[2]))

    # month coverage of each year, read from the index, which records every
    # month a file was seen for
    print("  month coverage per year:")
    cov = {}
    for y in years:
        months = idx["years"][str(y)].get("months", [])
        cov[y] = months
        print("    %d: %2d month(s)  %s" % (y, len(months),
              (months[0] + " .. " + months[-1]) if months else "-"))
    res["A5_sensitivity"] = {"slopes": a5, "months": cov}

    # ============================================================ ANALYSIS 6
    print("\n[6] fixed-grid Gini (grid fixed in geographic space)")
    allP = np.array([(v[0], v[1]) for y in years for v in yrs[y].values()], float)
    org = (allP[:, 0].min(), allP[:, 1].min())
    span = max(allP[:, 0].max() - org[0], allP[:, 1].max() - org[1])
    # A 20x20 grid over a city this size gives cells about
    # 4.9 km across and only a handful of occupied cells, so the Gini has almost
    # no resolution. We therefore report a ladder of resolutions, each with a
    # bootstrap interval, so the reader can see whether the shape survives
    # refinement or is an artefact of coarse binning.
    rng6 = np.random.default_rng(99)
    a6 = []
    ladder = [20, 30, 40, 50]
    for y in years:
        P = np.array([(v[0], v[1]) for v in yrs[y].values()], float)
        row = {"year": y}
        for nx in ladder:
            c = span / nx
            g = gini_fixed_grid(P, org, c, nx)
            # bootstrap over instruments, 500 draws
            boots = []
            for _ in range(500):
                idx = rng6.integers(0, len(P), size=len(P))
                gg = gini_fixed_grid(P[idx], org, c, nx)
                if np.isfinite(gg):
                    boots.append(gg)
            lo, hi = (np.percentile(boots, [2.5, 97.5])
                      if len(boots) > 20 else (float("nan"), float("nan")))
            row["g_%d" % nx] = g
            row["g_%d_ci" % nx] = [float(lo), float(hi)]
        n_occ = len({(int(np.floor((p0 - org[0]) / (span / 50))),
                      int(np.floor((p1 - org[1]) / (span / 50))))
                     for p0, p1 in P})
        row["occupied_50"] = n_occ
        a6.append(row)
        print("  %d  cells=%4.0f m | G(20)=%.3f G(30)=%.3f G(40)=%.3f G(50)=%.3f | 50x50 occupied=%d"
              % (y, span / 50, row["g_20"], row["g_30"], row["g_40"], row["g_50"], n_occ))
    res["A6_gini_fixed"] = a6

    # ============================================================ ANALYSIS 7
    print("\n[7] snapshot reconciliation and vehicle base rate")
    con = sqlite3.connect(DB)
    snap_ids = {str(r[0]).strip() for r in
                con.execute("SELECT raw_id FROM sensors") if r[0]}
    con.close()
    arch_ids = {i for y in years for i in yrs[y]}
    inter = snap_ids & arch_ids
    snap_only = snap_ids - arch_ids
    arch_only = arch_ids - snap_ids

    def theme_class(i):
        for y in years:
            if i in yrs[y]:
                tv = yrs[y][i][2]
                return tv.split("/")[0]
        return "?"

    veh_all = sum(1 for i in arch_ids if theme_class(i) == "Vehicles")
    veh_arch_only = sum(1 for i in arch_only if theme_class(i) == "Vehicles")
    base = 100.0 * veh_all / len(arch_ids) if arch_ids else 0.0
    omis = 100.0 * veh_arch_only / len(arch_only) if arch_only else 0.0

    # low-numbered test: are omitted identifiers numerically lower?
    def numeric(i):
        return int(i) if i.isdigit() else None

    om_num = [numeric(i) for i in arch_only]
    in_num = [numeric(i) for i in inter]
    om_num = [v for v in om_num if v is not None]
    in_num = [v for v in in_num if v is not None]
    mannwhitney = None
    if om_num and in_num:
        from scipy.stats import mannwhitneyu
        u, p = mannwhitneyu(om_num, in_num, alternative="two-sided")
        mannwhitney = {"u": float(u), "p": float(p),
                       "median_omitted": float(np.median(om_num)),
                       "median_matched": float(np.median(in_num))}

    res["A7_snapshot"] = {
        "snapshot_ids": len(snap_ids), "archive_ids": len(arch_ids),
        "matched": len(inter), "snapshot_only": len(snap_only),
        "archive_only": len(arch_only),
        "coverage_pct": 100.0 * len(inter) / len(arch_ids) if arch_ids else 0.0,
        "vehicle_base_rate_pct": base,
        "vehicle_omission_pct": omis,
        "low_numbered": mannwhitney,
    }
    print("  snapshot %d | archive %d | matched %d" % (len(snap_ids), len(arch_ids), len(inter)))
    print("  snapshot-only (absent from our census): %d" % len(snap_only))
    print("  archive-only  (the claimed omissions) : %d" % len(arch_only))
    print("  coverage of archive by snapshot       : %.1f%%"
          % (100.0 * len(inter) / len(arch_ids)))
    print("  vehicle base rate among all archive ids: %.1f%%" % base)
    print("  vehicle share of omitted              : %.1f%%" % omis)
    if mannwhitney:
        print("  Mann-Whitney on identifier value      : p=%.3g  median omitted=%.0f matched=%.0f"
              % (mannwhitney["p"], mannwhitney["median_omitted"],
                 mannwhitney["median_matched"]))

    pathlib.Path(a.out).write_text(json.dumps(res, indent=1))
    print("\nwritten %s" % a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
