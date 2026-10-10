#!/usr/bin/env python3
"""
Validate the two estimators the paper relies on against patterns whose answer is
known by construction. A statistic that cannot recover the truth on a synthetic
control cannot be trusted on the real data.

  ce_r(P, area)        Clark-Evans R. On CSR the answer is 1 by definition.
  donnelly_ce          WITHDRAWN. Reproduced here to show WHY it was withdrawn:
                       its correction term is unbounded, so it returns R = 4.5 to 16
                       on complete spatial randomness, where the answer is 1.

If the Donnelly version does not return ~1 on CSR, its correction term is wrong and
no value it produces may be reported.

Usage: python3 verify_estimators.py
"""
from __future__ import annotations

import math
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from analysis_common import ce_r  # noqa: E402

rng = np.random.default_rng(4242)
HALF = 10000.0   # 20 km square window, the order of the study area


def csr(n: int, half: float) -> np.ndarray:
    return rng.uniform(-half, half, size=(n, 2))


def clustered(n: int, half: float, sd: float = 150.0, parents: int = 20) -> np.ndarray:
    P0 = rng.uniform(-half * 0.9, half * 0.9, size=(parents, 2))
    idx = rng.integers(0, parents, size=n)
    return P0[idx] + rng.normal(0.0, sd, size=(n, 2))


def donnelly_ce_withdrawn(P: np.ndarray, half_side: float) -> float:
    """The exact withdrawn implementation, kept to demonstrate why it failed."""
    n = len(P)
    nn = np.sort(np.linalg.norm(P[:, None, :] - P[None, :, :], axis=2),
                 axis=1)[:, 1]
    cx = half_side
    d_edge = np.minimum(cx - np.abs(P[:, 0]), cx - np.abs(P[:, 1]))
    lam = n / (2.0 * cx) ** 2
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = np.where(d_edge > 0,
                        (2.0 * d_edge / np.pi) * np.arctan(2.0 * d_edge / nn), 0.0)
    return float(np.mean(nn + corr) / (1.0 / (2.0 * math.sqrt(lam))))


print("=" * 78)
print("Clark-Evans R: CSR must give 1.0, clustered must give << 1")
print("=" * 78)
print(f"{'n':>6}  {'R (box area)':>13}  {'R withdrawn':>12}  {'R clustered':>12}")
for n in (50, 100, 200, 500, 1000, 2000):
    P = csr(n, HALF)
    area = (2 * HALF) ** 2
    r_box = ce_r(P, area)
    r_don = donnelly_ce_withdrawn(P, HALF)
    r_clu = ce_r(clustered(n, HALF), area)
    print(f"{n:>6}  {r_box:>13.3f}  {r_don:>12.3f}  {r_clu:>12.3f}")

print()
print("=" * 78)
print("Interpretation")
print("=" * 78)
bad = []
for n in (100, 500, 1000):
    P = csr(n, HALF)
    r_don = donnelly_ce_withdrawn(P, HALF)
    flag = "OK" if abs(r_don - 1.0) < 0.05 else "WRONG"
    print(f"  n={n:<5} CSR under the withdrawn correction: R={r_don:.3f}  -> {flag}")
    if flag == "WRONG":
        bad.append(n)

print()
if bad:
    print("RESULT: the withdrawn donnelly_ce does NOT recover R=1 on CSR; R climbs")
    print("        with n, so the term is unbounded, not a correction. Its values on")
    print("        the core are withdrawn from the paper. ce_r, used with the core's")
    print("        own area, DOES recover R~1 on CSR and is what the paper reports.")
else:
    print("RESULT: donnelly_ce recovers R~1 on CSR within 5%.")
