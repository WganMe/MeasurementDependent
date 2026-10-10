#!/usr/bin/env python3
"""Figure C5: Theil T on theme counts.

Recovered from the scratch generator `make_census_figures.py`, which lived outside
this repository. See make_population_figure.py for why only three of its six
figures are kept.

The title previously read "between-theme imbalance", which is wrong: T over counts
is TOTAL imbalance, and because the number of themes K grows over the record, part
of the rise is mechanical rather than a concentration finding. The axis is pinned to
the years actually observed, so it no longer starts at 2012.

Everything is read from uo_census_results.json.

Writes: figures/figC5_theil.pdf
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
                     "figure.dpi": 300, "savefig.bbox": "tight", "axes.axisbelow": True})

Y = [r["year"] for r in D["per_year"]]
T = [r["theil_T_themes"] for r in D["per_year"]]


def main() -> int:
    fig, ax = plt.subplots(figsize=(5.0, 3.0))
    ax.bar(Y, T, color="#55a868", width=0.72)
    ax.set_xlabel("year")
    ax.set_ylabel("Theil $T$ across theme counts")
    ax.set_title("Total thematic imbalance, by Theil $T$\n"
                 "part of the rise is mechanical: the theme count grows",
                 fontsize=8.8)
    ax.set_xlim(min(Y) - 0.75, max(Y) + 0.75)
    ax.set_xticks(list(Y))
    ax.set_xticklabels([str(y) for y in Y], fontsize=7, rotation=45)
    fig.tight_layout()
    fig.savefig(OUT / "figC5_theil.pdf")
    plt.close(fig)
    print("wrote figures/figC5_theil.pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
