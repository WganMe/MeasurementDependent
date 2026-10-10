#!/usr/bin/env python3
"""Round 13: the multiscale function, done properly.

Three defects are fixed here, all found by a known-answer control.

  1. The L curve used for Figure 3 applied a RECTANGULAR count formula
     (K = A * pairs / (m(m-1))) inside a CONVEX-HULL window, with no edge
     correction. On a complete-spatial-randomness pattern inside the hull it
     returns a mean |L| of about 316 m where the answer is 0, drifting to
     -629 m at 2 km. The drifting CSR envelope in the figure is that bias.
  2. It was computed on IDENTIFIERS, while the paper's headline unit is the
     deduplicated location.
  3. The CSR envelope was drawn from `cent_in`, a homogeneous pattern, which is
     the comparison the paper itself calls uninformative.

We replace the estimator with Ripley's border correction on the polygon window,
which is valid for any window shape:

    K(r) = |W| * sum_{i in W_{-r}} #{ j != i : d_ij <= r } / (n * n_{-r})

where W_{-r} is the hull eroded by r. For a convex polygon this is the
intersection of half-planes shifted inward by r, so it is exact and cheap.

Controls are run first: CSR must give L ~ 0, clustered must give L > 0,
regular must give L < 0.

Writes: results_multiscale.json
"""
from __future__ import annotations

import json
import math
import pathlib

import numpy as np
from scipy.spatial import ConvexHull, cKDTree

from analysis_common import load_years

HERE = pathlib.Path(__file__).resolve().parent
RS = np.array([100., 250., 500., 750., 1000., 1500., 2000.])


def hull_edges(pts: np.ndarray):
    h = ConvexHull(pts)
    poly = pts[h.vertices]
    return poly, h.volume


def inward_lines(poly: np.ndarray):
    """Each edge as (unit inward normal, offset), ordered so the polygon is the
    intersection of n.x >= c."""
    out = []
    m = len(poly)
    centroid = poly.mean(axis=0)
    for k in range(m):
        a, b = poly[k], poly[(k + 1) % m]
        e = b - a
        n = np.array([-e[1], e[0]])
        n = n / np.linalg.norm(n)
        if np.dot(centroid - a, n) < 0:
            n = -n
        out.append((n, float(np.dot(n, a))))
    return out


def eroded_contains(P: np.ndarray, lines, r: float) -> np.ndarray:
    """Points of P at distance >= r inside every edge (i.e. in W_{-r})."""
    ok = np.ones(len(P), bool)
    for n, c in lines:
        ok &= (P @ n) >= (c + r)
    return ok


def L_border(P: np.ndarray, area: float, rs=RS, lines=None, poly=None):
    """Ripley's border-corrected L on a convex polygon window."""
    m = len(P)
    if m < 5 or lines is None:
        return np.full(len(rs), np.nan)
    tree = cKDTree(P)
    out = np.zeros(len(rs))
    for i, r in enumerate(rs):
        inside = eroded_contains(P, lines, r)
        n_er = int(inside.sum())
        if n_er < 5:
            out[i] = np.nan
            continue
        tot = 0
        for idx in np.nonzero(inside)[0]:
            tot += len(tree.query_ball_point(P[idx], r)) - 1
        K = area * tot / (m * n_er)
        out[i] = math.sqrt(max(K, 0.0) / math.pi) - r
    return out


def ids_of(d):
    return np.array([(v[0], v[1]) for v in d.values()], float)


def locs_of(d):
    return np.unique(np.round(ids_of(d), 1), axis=0)


def in_hull(P, poly):
    return eroded_contains(P, inward_lines(poly), 0.0)


def sample_hull(n, poly, rng):
    box = np.array([poly[:, 0].min(), poly[:, 1].min(),
                    poly[:, 0].max(), poly[:, 1].max()])
    out = []
    while len(out) < n:
        c = np.column_stack([rng.uniform(box[0], box[2], n * 2),
                             rng.uniform(box[1], box[3], n * 2)])
        out.extend(c[in_hull(c, poly)])
    return np.array(out[:n])


def main():
    idx = json.loads((HERE / "uo_archive_index.json").read_text())
    yrs = load_years(idx)
    years = sorted(yrs)
    allP = np.vstack([ids_of(yrs[y]) for y in years])
    poly, A = hull_edges(allP)
    lines = inward_lines(poly)
    rng = np.random.default_rng(20261003)
    res = {"years": years, "A_hull_m2": float(A), "rs": RS.tolist(),
           "n_hull_vertices": int(len(poly))}

    # ---------------------------------------------------------------- controls
    print("\n[A] controls: L_border must be 0 on CSR, >0 clustered, <0 regular")
    ctl = {}
    csr = sample_hull(300, poly, rng)
    Lc = L_border(csr, A, lines=lines)
    ctl["csr"] = Lc.tolist()
    print("  CSR n=300      : " + " ".join("%+7.1f" % v for v in Lc))

    # clustered: tight gaussian blobs
    n_blob = 40
    centres = sample_hull(n_blob, poly, rng)
    cl = np.vstack([c + rng.normal(0, 150, (8, 2)) for c in centres])
    cl = cl[in_hull(cl, poly)]
    clu = L_border(cl, A, lines=lines)
    ctl["clustered"] = clu.tolist()
    print("  clustered n=%3d  : " % len(cl) + " ".join("%+7.1f" % v for v in clu))

    # regular: jittered lattice
    gx = np.linspace(poly[:, 0].min(), poly[:, 0].max(), 26)
    gy = np.linspace(poly[:, 1].min(), poly[:, 1].max(), 26)
    GX, GY = np.meshgrid(gx, gy)
    lat = np.column_stack([GX.ravel(), GY.ravel()]) + rng.normal(0, 60, (GX.size, 2))
    lat = lat[in_hull(lat, poly)]
    reg = L_border(lat, A, lines=lines)
    ctl["regular"] = reg.tolist()
    print("  regular n=%3d    : " % len(lat) + " ".join("%+7.1f" % v for v in reg))
    res["controls"] = ctl
    print("  r (m)          : " + " ".join("%7.0f" % v for v in RS))

    # ------------------------------------------------------- paper's old curve
    print("\n[B] the estimator used in Figure 3, for comparison (CSR, n=300)")
    def L_old(P, area, rs):
        tree = cKDTree(P); m = len(P); out = []
        for r in rs:
            pr = tree.query_pairs(r, output_type="ndarray")
            k = area * len(pr) / (m * (m - 1)) if m > 1 else 0.0
            out.append(math.sqrt(k / math.pi) - r)
        return np.array(out)
    Lo = L_old(csr, A, RS)
    res["control_old_estimator"] = Lo.tolist()
    print("  old, CSR n=300 : " + " ".join("%+7.1f" % v for v in Lo))
    print("  mean |L| old = %.1f m   vs border-corrected %.1f m"
          % (np.mean(np.abs(Lo)), np.nanmean(np.abs(Lc))))

    # ------------------------------------------------------ L on locations
    print("\n[C] L(r) on DEDUPLICATED LOCATIONS, fixed hull, border-corrected")
    rows = []
    env = np.array([L_border(sample_hull(200, poly, rng), A, lines=lines)
                    for _ in range(199)])
    for y in years:
        P = locs_of(yrs[y])
        L = L_border(P, A, lines=lines)
        rows.append({"year": y, "n": int(len(P)),
                     "L": [None if not np.isfinite(v) else float(v) for v in L]})
        print("  %d n=%-4d : " % (y, len(P)) + " ".join(
            ("%+7.1f" % v) if np.isfinite(v) else "    n/a" for v in L))
    env_lo = np.nanpercentile(env, 2.5, axis=0)
    env_hi = np.nanpercentile(env, 97.5, axis=0)
    res["L_locations"] = {"rows": rows, "env_lo": env_lo.tolist(),
                          "env_hi": env_hi.tolist(),
                          "env_med": np.nanpercentile(env, 50, axis=0).tolist()}
    print("  CSR env lo     : " + " ".join("%+7.1f" % v for v in env_lo))
    print("  CSR env hi     : " + " ".join("%+7.1f" % v for v in env_hi))

    # where is L positive and above the envelope
    arr = np.array([[np.nan if v is None else v for v in r["L"]] for r in rows])
    print("\n  L > 0 at every scale (locations):",
          bool(np.all(arr > 0)))
    for i, r in enumerate(RS):
        col = arr[:, i]
        print("    r=%4.0f m : positive in %2d/14 years, above CSR env in %2d/14, min %+.1f max %+.1f"
              % (r, int((col > 0).sum()), int((col > env_hi[i]).sum()),
                 np.nanmin(col), np.nanmax(col)))

    # shape change 2020 vs 2026, normalised by the 2 km value
    print("\n[D] shape change: each year's curve normalised by its own 2 km value")
    norm = {}
    for r in rows:
        v = np.array([np.nan if x is None else x for x in r["L"]])
        if np.isfinite(v[-1]) and v[-1] != 0:
            norm[r["year"]] = (v / v[-1])
    for y in (2013, 2017, 2020, 2023, 2026):
        if y in norm:
            print("  %d : " % y + " ".join("%+7.2f" % x for x in norm[y]))
    res["normalised"] = {str(k): v.tolist() for k, v in norm.items()}

    json.dump(res, open(HERE / "results_multiscale.json", "w"), indent=1)
    print("\nwrote results_multiscale.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
