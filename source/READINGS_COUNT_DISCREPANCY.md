# The "155 million readings" figure — measured, and it does not match

**Status: VERIFIED DISCREPANCY. Needs an author decision before the PeerJ submission.**

**All 14 years are now counted** (2013–2026), the count method is validated against a real CSV
parser, and the 2026 archive is hash-verified against the manifest. Two errors made in earlier
versions of this file are recorded at the end, because the way they were made is the finding.

## The claim

`paper/main.tex` line 645, and therefore line 649 of the generated
`PeerJ/peerj-main.tex`:

> "We hold the complete local archive: 884 files covering 2013–2026, about 73.8 GB,
> **with 155 million readings in the 2026 year alone.**"

It is stated as fact, in the introduction, and it is **not** driven by a macro — the literal
number `155` is typed into the prose. `verify_paper_numbers.py` gates 23 macros; this is not one
of them, so nothing has been checking it.

## What the archive actually contains — complete count

Counted directly from every archive on disk. The method counts data rows as `lines - 1` per CSV;
each file has one header row. **Validated** by parsing every theme's first file with Python's
`csv.reader` and confirming `lines == csv_records` for all eight themes (Air Quality, Building,
Noise, People, Sensor Metrics, Vehicles, Water Level, Weather).

| Year | Bundles | Readings (measured) |
| --- | ---: | ---: |
| 2013 | 11 | 4,244,933 |
| 2014 | 19 | 8,371,091 |
| 2015 | 27 | 27,120,328 |
| 2016 | 41 | 175,377,835 |
| 2017 | 66 | 310,631,407 |
| 2018 | 75 | 309,802,130 |
| 2019 | 66 | 428,075,479 |
| 2020 | 75 | 468,184,233 |
| 2021 | 64 | 381,566,067 |
| 2022 | 48 | 372,547,165 |
| **2023** | 49 | **489,784,193** ← largest |
| 2024 | 45 | 261,525,899 |
| 2025 | 41 | 209,368,033 |
| **2026** | 257 | **176,254,027** |
| **Total** | **884** | **3,622,852,820** |

**The archive counted is the archive the paper cites.** `UO-archive-2026.zip` has
`sha256 dc4f94300ceb4119fe86fe04a9a422b3a8ed6dc921baa0df2db523615ab1ed35` and
7,751,816,063 bytes, matching `UO_ARCHIVE_MANIFEST.json` **exactly** — same bytes, same hash.
The manifest and `build_archive_index.py` were both built from it on 2026-10-02. The 884-file
total matches the manifest's `totals.files` exactly, which is an independent cross-check that the
same archive set was counted.

## Why the number does not match, in two separate ways

**1. The 2026 figure is wrong.** Measured **176,254,027**, not 155,000,000 — the stated value is
**88 %** of the true one. Not a rounding difference; a different number.

**2. The framing is wrong as well, and this is the larger problem.** The sentence singles out
2026 — *"in the 2026 year alone"* — implying it is the notable or largest year. It is neither:

| | Readings | Rank |
| --- | ---: | ---: |
| **2023** (largest) | **489,784,193** | 1 |
| 2020 | 468,184,233 | 2 |
| 2019 | 428,075,479 | 3 |
| … | | |
| **2026** | **176,254,027** | **10 of 14** |

**2026 ranks 10th of the 14 years, at 36 % of the largest year.** Nine of the fourteen years —
including every year from 2016 to 2025 except 2024 — publish more readings than 2026 does. And
2026 is a *partial* year: January to September at the snapshot. So the year chosen to illustrate
the archive's scale is among the smaller recent years, and the stated total for it is low.

## Two corrections to earlier versions of this file

Both were inferences drawn from an **incomplete** count, and both are wrong. They are recorded
rather than deleted, because the failure mode is the point: a partial count produced a confident
ranking that a fifth more counting reversed.

1. **"2017 is the largest year."** Written when only 2013–2017 had been counted. Wrong: four later
   years exceed it.
2. **"2020 is the largest year (468,184,233)."** Written when 2021–2025 were still running. Wrong:
   **2023** exceeds it by 21 million.

The pattern — infer a ranking from a prefix of the data — is exactly the error this project's own
chapter is about, and it is why the recommendation below prefers a claim that needs no ranking at
all.

## What was checked and ruled out

- **Not duplicate publication of one measurement.** `Plates In`, `Plates Matching` and `Plates
  Out` each have exactly 3,938,723 rows for January 2026 — suspiciously equal. Tested: the
  `Value` columns differ (`3.0/8.0/10.0` vs `4.0/1.0` vs `6.0/7.0/0.0`), so they are three
  distinct measurements, not one repeated. The equality is a shared sampling schedule.
- **Not a counting artefact of quoted newlines.** Verified against a strict CSV parser on all
  eight themes; no theme has multi-line fields that would inflate a line count.
- **Not the wrong archive vintage.** The sha256 matches the manifest, and both date from the
  same snapshot, so no growth between counting and pinning can explain it.

## What is *not* established

**What 155 million was intended to refer to.** It is not the 2026 total, and it is below both
2016 and 2017. Candidates that were tested and do **not** produce it: 2026 minus one month
(161,566,192), and 2026 at eleven-twelfths (161,566,191). It may be a remembered figure from an
earlier draft, a different aggregation, or an error. This file does not say which, because the
evidence does not.

## Recommendation

**Do not submit with the sentence as written.** It is a checkable factual claim about a public
archive, in the introduction of a paper whose Data Availability statement invites the reader to
the very data that contradicts it.

The **simplest and safest fix** is to drop the year-specific claim entirely and keep the archive
totals, which are already macro-driven and gated:

> "We hold the complete local archive: \num{\nArchiveFiles} files covering 2013--2026, about
> \SI{\nArchiveGB}{\giga\byte}."

If a reading count is wanted, it must be one of the measured values, not an estimate:

| Option | What it states | Basis |
| --- | --- | --- |
| **A — archive totals only** *(recommended)* | 884 files / 73.8 GB, no reading count | already gated by `verify_paper_numbers.py` |
| **B — 2026 corrected** | 176,254,027 readings in 2026 | measured; 2026 ranks 10th of 14 and is a partial year |
| **C — largest year** | 489,784,193 readings in 2023 | measured; 2023 is the largest |
| **D — the whole archive** | 3,622,852,820 readings over 884 files, 2013–2026 | measured; all 14 years counted |

Option **A** is recommended because it removes a number that no committed script derives, and
because the archive totals are already verified. **B** corrects the figure in place. **C** is the
strongest single-year scale claim, but names a year four years before the study's end and would
need its own justification. **D** is the strongest claim of all and needs no ranking — it is the
sum, which is what the sentence is trying to convey anyway. **D** is the best choice if a reading
count is genuinely wanted.

Whichever is chosen, a reading count should become a **macro** recomputed from the archive by a
committed script, so `verify_paper_numbers.py` gates it like the other 23. A bare integer in the
prose is what let this drift unnoticed: the 2026 figure is stated in the introduction, is
checkable in minutes against an archive the paper itself cites, and **nothing was checking it**.

---

*Measured 2026-10-09 by counting every CSV in each `UO-archive-YYYY.zip`, with the count method
validated against `csv.reader` per theme (8 of 8 themes, `lines == records`) and the 2026 archive
hash-checked against `UO_ARCHIVE_MANIFEST.json` (sha256 identical).*
