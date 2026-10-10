#!/usr/bin/env python3
"""Round 14: the four board-review items that need new computation rather than wording.

  [A] An edge-corrected single-index Clark--Evans R. The headline R is raw; the
      review asks whether edge bias changes over the record, since N and extent
      both move. We compute R three ways on the fixed hull: raw, Ripley's border
      correction (which discards reference points within d of the boundary), and a
      guard-area variant that discards a fixed margin. Donnelly's correction is
      not used: it assumes a rectangular window and returned 4.5-16 on CSR.

  [B] The 2026 endpoint. 2026 is a nine-month partial year and the archive's last
      month is a publishing-regime change. We report every headline quantity with
      and without 2026, so a reader can see how much of the result is the endpoint.

  [C] Theme-stratified clustering at the key years 2013, 2017, 2018, 2021 and 2026,
      to test whether the spatial trend is a composition artefact. Theme share
      moves from 58.5% to 73.0% and collapses to 16.8% in 2018, so this is a real
      confound.

  [D] The gap-filled roster sensitivity extended to the multiscale function and to
      the infill test, not only to R and the Gini.

Writes: results_edge.json
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

import numpy as np
from scipy.spatial import ConvexHull, cKDTree

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from analysis_common import load_years, ols_hac                      # noqa: E402
from analysis_multiscale import (L_border, hull_edges,           # noqa: E402
                                      inward_lines, ids_of, locs_of, RS)

HERE = pathlib.Path(__file__).resolve().parent
KEY_YEARS = (2013, 2017, 2018, 2021, 2026)


def theme_of(tv: str) -> str:
    return str(tv).split("/")[0]


# ------------------------------------------------------------------ [A]
def ce_border(P: np.ndarray, A: float, lines) -> float:
    """Ripley's border-corrected nearest-neighbour mean.

    A reference point is used only if its nearest neighbour lies inside the window,
    i.e. the point is at least d_i from the boundary. For a convex polygon that is
    the erosion of the hull by d_i, so the test is exact.
    """
    n = len(P)
    if n < 5:
        return float("nan")
    nn = cKDTree(P).query(P, k=2)[0][:, 1]
    keep = np.zeros(n, bool)
    for i, d in enumerate(nn):
        # is point i inside the hull eroded by d?
        ok = True
        for nrm, c in lines:
            if float(np.dot(P[i], nrm)) < c + d:
                ok = False
                break
        keep[i] = ok
    if keep.sum() < 5:
        return float("nan")
    d_bar = float(np.mean(nn[keep]))
    return d_bar / (1.0 / (2.0 * math.sqrt(n / A)))


def ce_guard(P: np.ndarray, A: float, lines, margin: float) -> float:
    """Nearest-neighbour mean over points at least `margin` inside the boundary."""
    keep = np.ones(len(P), bool)
    for nrm, c in lines:
        keep &= (P @ nrm) >= (c + margin)
    if keep.sum() < 5:
        return float("nan")
    nn = cKDTree(P[keep]).query(P[keep], k=2)[0][:, 1]
    return float(np.mean(nn)) / (1.0 / (2.0 * math.sqrt(len(P) / A)))


def main() -> int:
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    Y = np.array(years, float)
    allP = np.vstack([ids_of(yrs[y]) for y in years])
    poly, A = hull_edges(allP)
    lines = inward_lines(poly)
    rng = np.random.default_rng(20261003)
    res = {"years": years, "A_hull_m2": float(A)}

    def slope_of(v, ys):
        ys = np.asarray(ys, float)
        X = np.column_stack([np.ones_like(ys), ys])
        beta, se, r2, resid = ols_hac(v, X, 2)
        n, k = X.shape
        from scipy import stats
        tc = stats.t.ppf(0.975, n - k)
        so = math.sqrt((resid ** 2).sum() / (n - k) / ((ys - ys.mean()) ** 2).sum())
        p_ols = float(2 * stats.t.sf(abs(beta[1] / so), n - k))
        _, p_mk = stats.kendalltau(ys, v)
        return {"slope": float(beta[1]), "nw_ci": [float(beta[1] - tc * se[1]),
                                                   float(beta[1] + tc * se[1])],
                "ols_p": p_ols, "mk_p": float(p_mk)}

    # ---------------------------------------------------------------- A
    print("\n[A] edge-corrected single-index R on the fixed hull, locations")
    # Three estimators, and the difference between them matters. `plain` is the
    # headline estimator with no filtering at all. `inside` keeps only points
    # strictly inside the hull, which drops the handful sitting exactly on it --
    # and those are the most extreme sites, so the filter is already a correction.
    # `border` is Ripley's border correction, using each point's own
    # nearest-neighbour distance as its guard width. `guard500` uses a fixed 500 m
    # margin. Labelling the unfiltered series `raw` would be wrong, because a
    # strict >= test on the hull edges does drop points.
    plain, inside, bord, guard = [], [], [], []
    for y in years:
        P = locs_of(yrs[y])
        nn = cKDTree(P).query(P, k=2)[0][:, 1]
        plain.append(float(np.mean(nn)) / (1.0 / (2.0 * math.sqrt(len(P) / A))))
        inside.append(ce_guard(P, A, lines, 0.0))
        bord.append(ce_border(P, A, lines))
        guard.append(ce_guard(P, A, lines, 500.0))
    raw = plain  # the headline series, kept under its original name below
    print("  year  plain  inside  border  guard500")
    for i, y in enumerate(years):
        P = locs_of(yrs[y])
        nn = cKDTree(P).query(P, k=2)[0][:, 1]
        used = sum(1 for k, d in enumerate(nn) if all(
            float(np.dot(P[k], nrm)) >= c + d for nrm, c in lines))
        print("  %d  %.3f  %.3f   %.3f   %.3f     (n %d, border uses %d)"
              % (y, plain[i], inside[i], bord[i], guard[i], len(P), used))
    res["edge"] = {
        "plain": plain, "inside": inside, "border": bord, "guard500": guard,
        "trend": {k: slope_of(np.array(v), Y) for k, v in
                  (("plain", plain), ("inside", inside), ("border", bord),
                   ("guard500", guard))},
        "endpoint": {
            "plain": [plain[0], plain[-1]], "inside": [inside[0], inside[-1]],
            "border": [bord[0], bord[-1]], "guard500": [guard[0], guard[-1]],
        },
    }
    for k in ("plain", "inside", "border", "guard500"):
        t = res["edge"]["trend"][k]
        print("  %-10s slope %+.4f  NW [%+.4f, %+.4f]  OLS p %.3f  MK p %.3f"
              % (k, t["slope"], t["nw_ci"][0], t["nw_ci"][1], t["ols_p"], t["mk_p"]))

    # the control: an edge-corrected estimator must still return ~1 on CSR
    def sample_hull(n, poly_, rng_):
        box = np.array([poly_[:, 0].min(), poly_[:, 1].min(),
                        poly_[:, 0].max(), poly_[:, 1].max()])
        out = []
        while len(out) < n:
            c = np.column_stack([rng_.uniform(box[0], box[2], n * 2),
                                 rng_.uniform(box[1], box[3], n * 2)])
            keep = np.ones(len(c), bool)
            for nrm, cc in lines:
                keep &= (c @ nrm) >= (cc - 1e-9)
            out.extend(c[keep])
        return np.array(out[:n])
    ctl = {}
    for n in (100, 300, 700):
        Q = sample_hull(n, poly, rng)
        nnq = cKDTree(Q).query(Q, k=2)[0][:, 1]
        ctl[n] = {"plain": float(np.mean(nnq)) / (1.0 / (2.0 * math.sqrt(len(Q) / A))),
                  "inside": ce_guard(Q, A, lines, 0.0),
                  "border": ce_border(Q, A, lines)}
        print("  control CSR n=%3d : plain %.3f  inside %.3f  border %.3f  (all ~1.00)"
              % (n, ctl[n]["plain"], ctl[n]["inside"], ctl[n]["border"]))
    res["edge"]["control_csr"] = {str(k): v for k, v in ctl.items()}

    # ---------------------------------------------------------------- B
    print("\n[B] the 2026 endpoint: every headline quantity with and without it")
    keep25 = np.array([y != 2026 for y in years])
    b = {}
    for name, v in (("plain R", plain), ("inside R", inside),
                    ("border R", bord), ("guard R", guard)):
        a1 = slope_of(np.array(v), Y)
        a2 = slope_of(np.array(v)[keep25], Y[keep25])
        b[name] = {"with_2026": a1, "to_2025": a2}
        print("  %-10s with 2026 %+.4f (OLS p %.3f)   to 2025 %+.4f (OLS p %.3f)  MK p %.3f"
              % (name, a1["slope"], a1["ols_p"], a2["slope"], a2["ols_p"], a2["mk_p"]))
    res["endpoint"] = b

    # ---------------------------------------------------------------- C
    print("\n[C] theme-stratified clustering at the key years, locations")
    rows = []
    for y in KEY_YEARS:
        d = yrs[y]
        by = {}
        for k, v in d.items():
            by.setdefault(theme_of(v[2]), []).append((v[0], v[1]))
        row = {"year": y, "n_loc": int(len(locs_of(d))),
               "all_R": ce_guard(locs_of(d), A, lines, 0.0), "themes": {}}
        share = {t: len(p) / len(d) for t, p in by.items()}
        row["vehicle_share"] = share.get("Vehicles", float("nan"))
        print("  %d  all R = %.3f  n_loc=%d  vehicle share %.1f%%  themes: %s"
              % (y, row["all_R"], row["n_loc"], 100 * row["vehicle_share"],
                 ", ".join("%s %.0f%%" % (t, 100 * s) for t, s in
                           sorted(share.items(), key=lambda kv: -kv[1]))))
        for t, pts in sorted(by.items(), key=lambda kv: -len(kv[1])):
            Q = np.unique(np.round(np.array(pts, float), 1), axis=0)
            if len(Q) < 20:
                continue
            r = ce_guard(Q, A, lines, 0.0)
            row["themes"][t] = {"n_loc": int(len(Q)), "R": r,
                                "share": float(share[t])}
            print("      %-16s n_loc=%-4d R=%.3f  share %.1f%%" % (t, len(Q), r, 100 * share[t]))
        rows.append(row)
    res["theme_stratified"] = rows

    # is the trend present WITHIN each theme? that is the composition test
    print("\n  within-theme trend across the key years (does each theme fall?)")
    for t in ("Vehicles", "Weather", "Air Quality", "People"):
        v = [r["themes"][t]["R"] for r in rows if t in r["themes"]]
        ys = [r["year"] for r in rows if t in r["themes"]]
        if len(v) >= 4:
            sl = float(np.polyfit(ys, v, 1)[0])
            print("    %-16s R %s  slope %+.4f over the key years" %
                  (t, " ".join("%.3f" % x for x in v), sl))
    res["within_theme"] = {
        t: {"R": [r["themes"][t]["R"] for r in rows if t in r["themes"]],
            "years": [r["year"] for r in rows if t in r["themes"]]}
        for t in ("Vehicles", "Weather", "Air Quality", "People")}

    # ---------------------------------------------------------------- D
    print("\n[D] gap-filled roster: the multiscale function and the infill test")
    allids = sorted(set().union(*[set(yrs[y]) for y in years]))
    first = {i: min(y for y in years if i in yrs[y]) for i in allids}
    last = {i: max(y for y in years if i in yrs[y]) for i in allids}
    filled = {}
    for y in years:
        pts = []
        for i in allids:
            if first[i] <= y <= last[i]:
                v = yrs[first[i]][i] if i in yrs[first[i]] else None
                if v is None:
                    for yy in years:
                        if i in yrs[yy]:
                            v = yrs[yy][i]
                            break
                if v is not None:
                    pts.append((v[0], v[1]))
        filled[y] = np.unique(np.round(np.array(pts, float), 1), axis=0)
    Lrows = []
    for y in years:
        Lp = L_border(filled[y], A, lines=lines)
        Lp_obs = L_border(locs_of(yrs[y]), A, lines=lines)
        Lrows.append({"year": y, "n_filled": int(len(filled[y])),
                      "n_pub": int(len(locs_of(yrs[y]))),
                      "L_filled": [None if not np.isfinite(v) else float(v) for v in Lp],
                      "L_pub": [None if not np.isfinite(v) else float(v) for v in Lp_obs]})
    res["gapfilled_L"] = Lrows
    print("  L at 1 km, published vs gap-filled (locations):")
    for r in Lrows:
        i = list(RS).index(1000.0)
        print("    %d  pub %.0f  filled %.0f  (n %d -> %d)"
              % (r["year"], r["L_pub"][i], r["L_filled"][i], r["n_pub"], r["n_filled"]))
    pub1k = np.array([r["L_pub"][list(RS).index(1000.0)] for r in Lrows])
    fil1k = np.array([r["L_filled"][list(RS).index(1000.0)] for r in Lrows])
    print("  L(1km) slope pub %+.1f m/yr, filled %+.1f m/yr"
          % (np.polyfit(Y, pub1k, 1)[0], np.polyfit(Y, fil1k, 1)[0]))
    res["gapfilled_L_trend"] = {"pub_1km_slope": float(np.polyfit(Y, pub1k, 1)[0]),
                                "filled_1km_slope": float(np.polyfit(Y, fil1k, 1)[0])}

    # infill on the gap-filled roster
    inf = []
    prev = None
    for y in years:
        Q = filled[y]
        if prev is None:
            prev = Q
            continue
        key = {tuple(r) for r in prev}
        new = np.array([r for r in Q if tuple(r) not in key])
        if len(new) < 3:
            prev = Q
            continue
        pooled = np.vstack([prev, new])
        labels = np.array([0] * len(prev) + [1] * len(new))
        obs = float(np.median(cKDTree(prev).query(new, k=1)[0]))
        sims = []
        for _ in range(199):
            perm = rng.permutation(len(pooled))
            lab = labels[perm]
            t2 = cKDTree(pooled[lab == 0])
            sims.append(float(np.median(t2.query(pooled[lab == 1], k=1)[0])))
        sims = np.array(sims)
        inf.append({"year": y, "n_new": int(len(new)), "obs_median_m": obs,
                    "env_lo": float(np.percentile(sims, 2.5)),
                    "env_hi": float(np.percentile(sims, 97.5))})
        prev = Q
    above = sum(1 for r in inf if r["obs_median_m"] > r["env_hi"])
    inside = [r["year"] for r in inf if r["obs_median_m"] <= r["env_hi"]]
    res["gapfilled_infill"] = {"rows": inf, "n_above": above, "n": len(inf),
                               "inside": inside}
    print("  infill on the gap-filled roster: above the envelope in %d of %d pairs, inside in %s"
          % (above, len(inf), inside))

    json.dump(res, open(HERE / "results_edge.json", "w"), indent=1)
    print("\nwrote results_edge.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
