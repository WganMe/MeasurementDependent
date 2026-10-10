# PeerJ submission

Target: **PeerJ** (main journal — *not* PeerJ Computer Science), publisher PeerJ Inc. / Taylor &
Francis. SCIE, IF 2.9; carries the **"Spatial and Geographic Information Science"** subject
overlay ("geocomputation and applied spatial statistics"). PeerJ evaluates on **methodological
soundness, not novelty** — which removes the paper's one real weakness. See
`source/admin/editorial/PEERJ_ASSESSMENT.md`.

This directory is **generated**, not hand-edited. One command rebuilds everything:

```sh
./build.sh
```

It regenerates the three documents from `source/`, typesets them, checks the result and
builds the upload bundle. **It exits non-zero rather than shipping a half-built document.**

Doing it by hand, in this order:

```sh
cd source && python3 convert_to_peerj.py && cd ..   # ../peerj-main.tex, ../peerj-si.tex, ../figures/
source/make_peerj_cover.py                          # ../peerj-cover.tex (also run by convert)
export PATH=/usr/local/texlive/2026/bin/x86_64-linux:$PATH
pdflatex -interaction=nonstopmode peerj-main.tex    # 1st pass writes the .aux
bibtex peerj-main                                   # reads the .aux, writes the .bbl
for i in 1 2 3; do pdflatex -interaction=nonstopmode peerj-main.tex; done
python3 make_peerj_bundle.py                        # dist/PeerJ_submission_<date>/ + .zip
```

**The order matters, and two passes are not enough.** BibTeX must run after a pass that has
written the `.aux`, and LaTeX only reads the `.bbl` on a pass after BibTeX. Running
`pdflatex` twice produced *"No file peerj-main.bbl"* on the first pass and left **72
citations undefined and the paper at 19 pages instead of 22**. Three passes resolve the 39
cross-reference labels.

`bibtex peerj-si` is skipped by `build.sh`: the supplement is tables-only, has no
`\citation` commands, and BibTeX treats that as an error and exits 2.

## Layout

```text
PeerJ/                     <- THIS FOLDER IS THE REPOSITORY ROOT
  peerj-main.tex/.pdf      the manuscript            (generated; upload as 1_manuscript.pdf)
  peerj-si.tex/.pdf        the supplement            (generated; upload as 2_supplemental_information_S1.pdf)
  peerj-cover.tex/.pdf     the author cover page     (generated; upload separately)
  figures/                 four cited figure PDFs, each also as "Figure N.pdf"
  references.bib           bibliography
  wlpeerj.cls              the official PeerJ class
  portal-values.md         values the portal asks for but the manuscript does not carry
  make_peerj_bundle.py     builds dist/
  dist/                    the upload bundle (rebuilt, not hand-edited)
  source/                  the generators AND the analysis: main.tex, paper_source.py,
                           analysis_*.py, results_*.json, admin/, archive/
```

## Deliverables

| File | What it is |
| --- | --- |
| `peerj-main.tex` / `.pdf` | The manuscript in the PeerJ `wlpeerj` class, line-numbered for review. 22 pp. |
| **`peerj-si.tex` / `.pdf`** | **The Supplementary Material** in `wlpeerj`, 19 S-numbered sections of robustness tables. 17 pp. |
| **`peerj-cover.tex` / `.pdf`** | **The Author Cover Page** PeerJ's Author Instructions require. 2 pp. Uploaded separately; see below for why it is not a page of the manuscript. |
| `wlpeerj.cls` | The official PeerJ class (from `LaTeX_Template_for_PeerJ_Journal_Submissions.zip`), kept in this folder *and* beside the sources in `source/`. |
| `references.bib` | Bibliography, `mdpi_si` (Symmetry SI) entry removed. |
| `figures/` | The four **cited** figure PDFs, each also written under PeerJ's `Figure N.pdf` filename convention. The `N` is the **citation order in the manuscript**, not the alphabetical order of the source slugs: `Figure 1.pdf` is the merge-tolerance figure and `Figure 4.pdf` is the study area. |

**The submission is the manuscript, the supplement AND the cover page.** The main text points to
the supplement 12 times, and PeerJ publishes the supplement as a separate file; the
`SUPPLEMENTAL INFORMATION` section in the main text states that.

**Why the cover page is a separate document.** PeerJ's submission checklist asks for author
contact details, a prior-dissemination statement and reviewer suggestions. Folding those into
`peerj-main.tex` would put them into the version of record, since PeerJ does not strip a page
from the published PDF. It is therefore generated as its own file by
`source/make_peerj_cover.py`, which parses the title, authors, affiliations and
corresponding e-mail **out of `peerj-main.tex`** so the two cannot contradict each other.

## Verified against PeerJ's published requirements (2026-10-09)

Read from `peerj.com/journals/peerj/author-instructions/` and `/policies/`, not from memory.

| Requirement (PeerJ's words) | Status |
| --- | --- |
| *"All figures must be cited in the main text."* | **now met** — the five uncited figures are no longer shipped (see below) |
| *"Include figure numbers in filenames e.g., 'Figure 1.png'."* | **met** — `Figure 1.pdf` … `Figure 4.pdf` written alongside the source names |
| *"When citing use the abbreviation 'Fig.'"* / *"When starting a sentence… use 'Figure 1'."* | **met** — 6 `Fig.`, 1 sentence-initial `Figure` |
| *"All tables must be cited in the main text."* | met — 7 tables, all cited |
| *"Author Cover Page"* | **met** — `peerj-cover.tex` |
| **Generative AI:** *"Use of AI tools to assist copyediting and language refinement is permitted."* The declaration must carry **four** elements: (a) originality and accuracy confirmed, (b) tool name and version, (c) terms of use checked and suitability confirmed, (d) authors take full responsibility incl. references | **now met** — the main text carried only (b); (a), (c) and (d) were **missing** and have been added. The supplement now carries its own statement, because a reader who downloads only the supplement would otherwise find none |
| *"Supplemental Files should not exceed 50 MB in total"* | met — the SI PDF is ~170 KB |

### Five figure files were being shipped without being cited

`figC3_gini_ci`, `figC4_theme_drift`, `figC5_theil`, `figC6_leave_one_out` and `figC7_lcurve`
were generated by `make_census_figures.py` and copied into the bundle by
`shutil.copytree(src / "figures", ...)`. **PeerJ requires every figure to be cited in the main
text**, and an uploaded uncited figure is a defect a reviewer can see.

Checked rather than assumed: the Gini and Theil **results** are in the main text as prose and
tables; theme-drift, leave-one-out and L-curve appear in **neither** manuscript. So they are
unused assets, not lost content. The copy is now driven by the `\includegraphics` calls in the
generated `.tex`, and any uncited file is **reported** at conversion time rather than shipped:

```console
figures: 4 cited and copied, also as Figure 1.pdf, Figure 2.pdf, Figure 3.pdf, Figure 4.pdf
figures NOT cited, therefore not shipped: figC3_gini_ci.pdf, ... figC7_lcurve.pdf
```

A figure cited but absent now **aborts the conversion** instead of silently producing a build
without it.

## What changed vs the MDPI source

- `\documentclass[fleqn,10pt,lineno]{wlpeerj}` — **`lineno` is required for review**.
- Front matter: `\title`, `\author[n]{}`, `\affil[n]{}`, `\corrauthor[n]{}{email}`, `abstract`
  environment, then `\flushbottom\maketitle\thispagestyle{empty}`.
- **Keywords are dropped** — `wlpeerj.cls` disables the keywords block (the official sample has it
  commented out). PeerJ collects Subjects/Keywords through its submission portal instead.
- **Sections are UNNUMBERED** (`\section*{}`), and every `Section~\ref{}` was replaced by a short
  noun phrase. This matches PeerJ's published style: the template writes `\section*{Introduction}`
  and a published PeerJ paper (20977) carries `INTRODUCTION`/`RESULTS`/`CONCLUSION` with **zero**
  numeric `Section N` references. (Numbering is *permitted* by the class but is not PeerJ's style.)
- Citations: the same Harvard conversion as the IJGIS build (29 `\citep`, 12 `\citet`,
  6 `\citeyearpar`), rendering as `(Author et al., 2024)`.

  > **This line claimed the rendering was "confirmed identical to PeerJ's" and it was not.**
  > For the whole life of this build the citations rendered *without* the comma —
  > `(Osamy et al. 2022)` — because `main.tex` carries `\bibpunct[, ]{(}{)}{;}{a}{}{,}`,
  > which overrides the class and removes it. Nobody compared the two. See
  > [Fixed 2026-10-11](#fixed-2026-10-11--citations-rendered-without-peerjs-comma) below; the
  > claim is now enforced by a check on the built PDF, not by this sentence.
- Back matter as unnumbered sections in PeerJ's order: Funding, Author Contributions, Competing
  Interests, Data Availability, Supplemental Information, contributor notes, AI declaration, then
  Acknowledgments + AI Use Disclosure, then References.

**Every number, table and figure is unchanged.**

## Defects found by comparing against a real PeerJ paper — both fixed

Compared our PDF against a newly published PeerJ paper (`peerj-20977.pdf`, in this folder) and the
official template, in both text and rendered form:

1. **Coloured link boxes around every citation** — `hyperref` (added because `wlpeerj.cls` has no
   `\url`) draws green borders by default. PeerJ papers have none. Fixed with
   `\usepackage[hidelinks]{hyperref}`.
2. **Numbered sections and numeric cross-references** — our first build emitted `Section 3.3` etc.
   PeerJ uses unnumbered headings and no numeric references. Fixed: all sections starred, and the
   23 `Section~\ref{}` references replaced by short noun phrases.

## Visual comparison against `peerj-20977.pdf` (2026-10-09)

Read page-by-page against the published paper and PeerJ's Author Instructions. Three further
deviations found and fixed in the converter (so the IJGIS build got them too):

1. **Figure citations.** PeerJ's instructions state plainly: *"When citing use the abbreviation
   'Fig.'. When starting a sentence with a citation, use 'Figure 1'."* The manuscript wrote
   `Figure~\ref{}` everywhere. Now mid-sentence citations render `Fig. 1`, and the one
   sentence-initial citation keeps `Figure`. (Captions correctly stay `Figure N`, and the class
   supplies the caption period — verified with a minimal test document.)
2. **Back-matter wrapper.** The published paper groups every declaration under one heading,
   `ADDITIONAL INFORMATION AND DECLARATIONS`, with the subsections `Funding`, `Grant Disclosures`,
   `Competing Interests`, `Author Contributions`, `Data Availability`, `Supplemental Information`.
   Ours had loose top-level sections and no `Grant Disclosures`. Now matches, with the grant number
   pulled from the funding statement rather than retyped.
3. **Duplicate AI statement.** The converter appended the structured AI disclosure *and* the source
   Acknowledgments already carried an inline Copilot sentence, so two AI statements were printed.
   Consolidated to one, inside the declarations wrapper.

Verified: main 22 pp, SI 17 pp, **0 errors, 0 undefined, 0 overfull**; the back-matter heading
sequence matches `peerj-20977.pdf` exactly; `Fig.`/`Figure` split follows the documented rule.

## PeerJ-specific requirements — status

| Requirement | Status |
| --- | --- |
| Line numbering for review | Added (`lineno` class option) |
| Single manuscript (PeerJ is **not** double-anonymous — no separate anonymous copy) | N/A |
| **Open data and code at submission** (PeerJ policy requires raw data, code, protocols) | Zenodo deposit + third-party Newcastle readings (CC BY 4.0) — Data Availability statement present |
| **Reviews are published** alongside the article | Noted — author's choice |
| Figures uploaded as separate files, one per figure (300 dpi on resubmission) | Figures are separate PDFs in `figures/` — upload individually |
| Figure/table citation style (`Fig.`, `Table 1`) | **Met** — counted in the built PDF: 5 mid-sentence `Fig.` (`Fig. 1`, `Fig. 2`, `Fig. 4`), the 4 captions read `Figure N.`, and all 7 tables are cited as `Table N` |
| Manuscript and Source files: *"Complete PDF manuscript, TEX, BIB, hi-res figures and tables"* | **Met** — the loose `.tex` and `.bib` are both named accepted types; only `wlpeerj.cls` is not, and it is inside **`source_main.zip`** and **`source_si.zip`** |
| One source archive per document (the portal has two source slots) | **Met** — `source_main.zip` (tex + bib + class + `figures/`) typesets to 22 pp alone; `source_si.zip` (tex + class) typesets to 17 pp alone. Both proved from an empty directory. `peerj-cover.tex` is in neither: the cover is uploaded on its own |
| Portal **Title** ≤ 250 characters | Met — 80. Extracted to `portal-fields.md` |
| Portal **Short Title** ≤ 50 characters | Met — 45. The portal is the only thing that asks for one, so it is a recommendation, not read from the paper |
| Portal **Abstract** ≤ **2000 characters** (not words), no linebreaks, special characters correct | Met — **1287** characters, 199 words, one line. Extracted from the built PDF, with U+2212 MINUS SIGN normalised to an ASCII hyphen |

## Fixed 2026-10-09 — two publishable defects

Both were **in the submitted PDF** and would have been published. Both came from the shared
constants in `source/paper_source.py`, so nothing else checked the generated output;
both are fixed at source and the output regenerated.

1. **An author-only instruction printed in the manuscript.** `Notes on contributors` ended with
   *"Each note is to be expanded by the author to a short biography before submission."* That is
   an instruction to the author, not text for a reader — and PeerJ does **not** publish
   contributor biographies at all (the real PeerJ paper goes *Author Contributions* → *References*
   with no such section; verified against `peerj-20977.pdf`). The `\emph{...}` instruction is
   removed; the contributor notes themselves are kept as factual affiliations.
2. **An unfilled tool-version placeholder.** The Generative AI Use Disclosure read
   `Tool: GitHub Copilot, version VERIFY-VERSION-BEFORE-SUBMISSION`. Replaced with the real
   installed version, **0.69.0** (read from the extension's `package.json`).

A guard was added to `convert_to_peerj.py` (and mirrored in the source constants) that
**refuses to finish** if the generated `.tex` contains `VERIFY-VERSION`, `PLACEHOLDER`, `XXX`,
`FIXME`, `TODO`, or *"to be expanded by the author"*. Proven by injecting the placeholder:
the converter exits non-zero with a clear message.

## Still to do before uploading (author decisions)

1. Retitle (optional for PeerJ — novelty is not judged — but helps discoverability).
2. ~~Contributor biographies~~ — **done**: not required by PeerJ, and the instruction removed.
3. Reconcile the Data Availability statement with PeerJ's open-data policy and the Zenodo DOI
   (the DOI `10.5281/zenodo.23099939` resolves; statement present).
4. Institutional email is not a PeerJ requirement (unlike IJGIS), but a valid corresponding
   address is needed — `walnahari0004@stu.kau.edu.sa` is present.
5. ~~The two open numbers~~ — **both closed 2026-10-10.** Archive basis is **884 files /
   73.8 GB**, gated by `verify_paper_numbers.py` from `UO_ARCHIVE_MANIFEST.json`.

## Fixed 2026-10-10 — a wrong figure in the introduction

The manuscript said *"with 155 million readings in the 2026 year alone"*. That was a **bare
integer typed into the prose**, not a macro, so `verify_paper_numbers.py` never gated it. It was
counted from the archive and is **wrong twice over**:

| | Measured | Claimed |
| --- | ---: | ---: |
| 2026 readings | **176,254,027** | 155,000,000 (88 % of the truth) |
| 2026 rank among the 14 years | **10th of 14** | implied to be the notable year |
| Largest year (2023) | **489,784,193** | — |

**The framing was the worse error.** 2026 is *not* the largest year and is a partial year
(nine months); it publishes 36 % of 2023's total. Nine of the fourteen years exceed it.

**The fix:** the sentence now states the **whole-archive total, 3,622,852,820 readings**, which
needs no ranking of years and therefore cannot repeat the mistake. It is a macro
(`\nArchiveReadings`) and `verify_paper_numbers.py --with-archive` recomputes it by counting
every CSV in every archive — so it is now gated like the other 23.

**Evidence:** [`source/READINGS_COUNT_DISCREPANCY.md`](source/READINGS_COUNT_DISCREPANCY.md).
Count method validated against `csv.reader` on all eight themes; the 2026 archive's sha256
matches `UO_ARCHIVE_MANIFEST.json` exactly, and the counted file total (884) matches the
manifest, so the same archive set was counted.

> **Two corrections are recorded in that file rather than hidden.** Earlier versions named 2017,
> then 2020, as the largest year. Both were inferences from a *partial* count, and both were
> wrong. The pattern — ranking from a prefix of the data — is the same error this paper's own
> Chapter 1 is about, and it is why the fix uses a total instead of a year.

## Build (standalone)

```sh
export PATH=/usr/local/texlive/2026/bin/x86_64-linux:$PATH
for i in 1 2; do pdflatex -interaction=nonstopmode peerj-main.tex; done
bibtex peerj-main
for i in 1 2; do pdflatex -interaction=nonstopmode peerj-main.tex; done
```

Verified: 22 pp main + 17 pp supplement, **0 errors, 0 undefined citations, 0 overfull**.

## Fixed 2026-10-11 — citations rendered without PeerJ's comma

PeerJ writes `(Osamy et al., 2024)`. This manuscript printed `(Osamy et al. 2022)` — no
comma — for the entire life of the build, while the README above asserted the rendering was
"identical to PeerJ's". The claim was never tested.

**Cause.** `main.tex` carries its own punctuation directive:

```latex
\bibpunct[, ]{(}{)}{;}{a}{}{,}
```

`wlpeerj.cls` loads `natbib` and sets `\bibliographystyle{apalike}`, which already produces
the comma form. The source's `\bibpunct` **overrides** it and drops the comma.

**Measured, not inferred.** A minimal document using the class alone renders
`(Clark and Evans, 1954)`; adding that one `\bibpunct` line renders `(Clark and Evans 1954)`.
So the correct action for `wlpeerj` is to *delete* the source's punctuation line and let the
class supply its own. `convert_to_peerj.py` now does exactly that.

**Guarded.** `make_peerj_bundle.py` counts both forms in the built PDF and refuses to build
if the comma-less form dominates, because the style is decided by `natbib` at typesetting
time — a source file that looks correct can still print the wrong form.

```text
citations: 14 with a comma, 0 without (PeerJ writes "(Author, 2024)")
```

Verified by re-injecting `\bibpunct` into the generated `.tex`: the build exits non-zero.

## Fixed 2026-10-11 — the bundle shipped Figure 1 and Figure 4 swapped

`convert_to_peerj.py` names the uploaded figures `Figure N.pdf` from the order the manuscript
**cites** them; `make_peerj_bundle.py` named them from a plain `sorted()`, which is
**alphabetical**. The two rules are not the same here, because the slugs are not cited in slug
order:

| Manuscript | Cited as | Correct file | Bundle used to ship |
| --- | --- | --- | --- |
| `figC8_tolerance.pdf` | Fig. 1 | `Figure 1.pdf` | `Figure 1.pdf` = *study area* (wrong) |
| `figC1_population.pdf` | Fig. 2 | `Figure 2.pdf` | correct (coincidence) |
| `figC2_clustering.pdf` | Fig. 3 | `Figure 3.pdf` | correct (coincidence) |
| `figC0_study_area.pdf` | Fig. 4 | `Figure 4.pdf` | `Figure 4.pdf` = *tolerance* (wrong) |

So a reviewer comparing `Figure 1.pdf` against the text that calls it "the merge tolerance"
would have found the study area. **The bug was invisible to the bundle's own check**, which
compared *sets* of files and not their order, and to the README, which asserted the numbering
was right.

Fixed at the cause: `make_peerj_bundle.py` now reads the order from the `\includegraphics`
calls (the same rule the converter already used) and **refuses to build** unless the
converter's `Figure N.pdf` file hashes equal the source file it should be. The two scripts can
no longer disagree, because one checks the other.

## Fixed 2026-10-11 — two abstracts, three different word counts

The cover page said the abstract was **197** words and `portal-values.md` said **198**, for the
same abstract. The rendered PDF holds **199**. Each number was computed independently and both
were wrong.

The cause in the cover page was a substitution that removed `\SI{25}{\meter}` **with its
arguments**, so numbers dropped out of the count. The count is now one function,
`source/paper_source.py:abstract_word_count`, which expands the manuscript's own numeric macros
(`\rDrop` → 67) and keeps the first argument of `\num` and `\SI`, so `\SI{25}{\meter}` reads
"25 m" as a reader sees it. The cover page and the bundle both import it, and
`make_peerj_bundle.py` **refuses to build** if `portal-values.md` or `peerj-cover.tex` states a
different length. Verified by breaking each of them in turn: both now exit non-zero.
