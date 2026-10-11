#!/usr/bin/env python3
"""Figure C4: thematic composition drifting, including the 2018 interruption.

Recovered from the scratch generator `make_census_figures.py`, which lived outside
this repository. See make_population_figure.py for why only three of its six
figures are kept.

Everything is read from uo_census_results.json.

Writes: figures/figC4_theme_drift.pdf
"""
from __future__ import annotations

import json
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

matplotlib.rcParams["pdf.fonttype"] = 42   # embed outlines, not Type 3 bitmaps

HERE = pathlib.Path(__file__).resolve().parent
D = json.loads((HERE / "uo_census_results.json").read_text())
OUT = HERE / "figures"
OUT.mkdir(exist_ok=True)

plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.3,
                     "figure.dpi": 300, "savefig.bbox": "tight", "axes.axisbelow": True,
                     "axes.unicode_minus": False})

Y = [r["year"] for r in D["per_year"]]
V = [r["vehicle_pct"] for r in D["per_year"]]


def main() -> int:
    fig, ax = plt.subplots(figsize=(5.4, 3.2))
    ax.plot(Y, V, "o-", color="#4c72b0", lw=1.8, ms=4, label="vehicles (% of instruments)")
    ax.plot(Y, [r["top_theme_pct"] for r in D["per_year"]], "s--", color="#8172b2",
            lw=1.2, ms=3, label="largest theme (% of instruments)")
    i18 = Y.index(2018)
    ax.annotate("2018: vehicle share collapses to %.1f%%\n(weather rises 149→169 instruments)" % V[i18],
                (2018, V[i18]), textcoords="offset points", xytext=(18, 22),
                fontsize=6.5, arrowprops=dict(arrowstyle="->", lw=0.7, color="0.4"))
    ax.set_ylim(0, 100)
    ax.set_xlabel("year")
    ax.set_ylabel("share of instruments (%)")
    ax.set_title("Thematic composition is not stable over time", fontsize=9)
    ax.legend(fontsize=6.8, loc="lower left")
    fig.savefig(OUT / "figC4_theme_drift.pdf")
    plt.close(fig)
    print("wrote figures/figC4_theme_drift.pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
