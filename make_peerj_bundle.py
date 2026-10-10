#!/usr/bin/env python3
"""Assemble the PeerJ submission upload bundle.

Writes dist/PeerJ_submission_<date>/ with the three PDFs the portal asks for, the figures
under PeerJ's "Figure N" names, the LaTeX sources, the checksums and the portal values.
Refuses to build if a PDF is older than its source, or if the manuscript cites a figure
that is not shipped.
"""
import datetime
import hashlib
import os
import re
import shutil
import subprocess
import sys
import zipfile

PJ = os.path.dirname(os.path.abspath(__file__))
DAY = datetime.date.today().isoformat()
NAME = "PeerJ_submission_" + DAY
OUT = os.path.join(PJ, "dist", NAME)

UPLOADS = {
    "peerj-main.pdf": "1_manuscript.pdf",
    "peerj-si.pdf": "2_supplemental_information_S1.pdf",
    "peerj-cover.pdf": "3_author_cover_page.pdf",
}
SOURCES = ["peerj-main.tex", "peerj-si.tex", "peerj-cover.tex", "references.bib",
           "wlpeerj.cls"]

START = """# PeerJ submission bundle ({day})

Created by `make_peerj_bundle.py`. Every file below was built from `peerj-*.tex` in this
folder and checked with pdfLaTeX.

## Upload these three PDFs, in this order

| This file | Portal file type | What it is |
| --- | --- | --- |
| `1_manuscript.pdf` | Manuscript | The paper, 22 pages, line-numbered for review. |
| `2_supplemental_information_S1.pdf` | Supplemental File | The supplement, 17 pages. The main text names it *Supplemental Information (S1)*. |
| `3_author_cover_page.pdf` | Author Cover Page | Title, authors, affiliations, corresponding e-mail, prior dissemination, reviewer suggestions. |

## Every file, checked against PeerJ's accepted types

PeerJ publishes two lists: *Manuscript and Source files* (complete PDF manuscript; TEX, BIB,
hi-res figures and tables) and *Supplemental Files* (Figures: `jpg png eps psd pdf`; Tables and
Documents: `docx doc odt rtf txt tex pdf`, plus `xls xlsx ods odt csv` for tables; Datasets:
`fasta seq zip tar.gz` or any type above). It then says: *"For other file types, please upload
a zip file containing the file you want to upload."*

| This bundle | PeerJ list | Type |
| --- | --- | --- |
| `1_manuscript.pdf` | Manuscript | PDF — accepted |
| `3_author_cover_page.pdf` | Manuscript | PDF — accepted |
| `figures/Figure 1.pdf` … `Figure 4.pdf` | Manuscript (figures) | PDF — accepted |
| `2_supplemental_information_S1.pdf` | Supplemental Files | PDF — accepted |
| `latex_source/*.tex` | Manuscript and Source files | TEX — accepted (the portal says so by name) |
| `latex_source/references.bib` | Manuscript and Source files | BIB — accepted (the portal says so by name) |
| `latex_source/wlpeerj.cls` | — | **CLS is the one type PeerJ does not name.** Send it inside `latex_source.zip` |
| `latex_source.zip` | Supplemental Files (Datasets) | ZIP — accepted; holds all five sources |

Every file in this bundle is an accepted type except `wlpeerj.cls`, and that one is covered
by `latex_source.zip`, which PeerJ accepts under Datasets.

`latex_source/` is kept loose here for reading. The `.tex` and `.bib` in it are uploadable
as they are; only the `.cls` needs the zip around it, so **upload `latex_source.zip`** and the
typing is right either way.

## Upload the four figures individually

Upload the four files in `figures/` one at a time, as the Manuscript file type. PeerJ asks
for figures as separate files under the names `Figure 1`, `Figure 2`, and so on; the source
names (`figC0_study_area.pdf`, ...) are kept beside them.

`Figure N.pdf` is named by the order the manuscript CITES the figures, not alphabetically.
The two are different here: `Figure 1.pdf` is the merge-tolerance figure (cited first) and
`Figure 4.pdf` is the study area (cited last). Keep the pairs together when uploading.

## Source files: send the zip, or the .tex and .bib direct

PeerJ's *Manuscript and Source files* section asks for "Complete PDF manuscript, TEX, BIB, 
hi-res figures and tables", so `.tex` and `.bib` are named accepted types and can be uploaded
as they are. `.cls` is the single file in this bundle that PeerJ does not name; its rule for
that case is *"For other file types, please upload a zip file containing the file you want to
upload."* So:

- `latex_source.zip` — **upload this** if PeerJ asks for the sources. One upload, all five
  files, and every type in it is acceptable inside the zip.
- `latex_source/` — the same five files loose, kept for reading here. Fine to upload as-is
  except for `wlpeerj.cls`.

Do not upload `peerj-main.tex` on its own in any case: it will not compile without
`wlpeerj.cls` and `references.bib`.

## Portal values

Two files cover the portal:

- `portal-fields.md` — the **Title**, **Short Title** and **Abstract** as paste-ready text.
  The portal's Title/Abstract tab is not the manuscript: they are plain-text fields, the
  abstract limit is **2000 characters rather than 2000 words**, and the checklist warns about
  linebreaks and special characters. All three values are extracted from the built PDF, so
  paste them rather than copying out of the PDF by hand.
- `portal-values.md` — the title, abstract, subjects, keywords, authors, affiliations, ORCIDs
  and the data DOI, copied from the manuscript rather than retyped. Nothing in this bundle
  needs a decision at upload time except the subjects, which the portal asks you to choose
  from its own list.

## Check before you upload

- `SHA256SUMS.txt` lists every file, so you can confirm the upload matches this bundle.
- The build summary is in `build-report.txt`: page counts and the error, undefined-reference
  and overfull-box counts for each PDF.

## Still open (author decisions, not file defects)

- Optional retitle, for discoverability. PeerJ does not judge novelty, so a descriptive title
  is fine either way.
"""


def run(cmd):
    return subprocess.run(cmd, cwd=PJ, capture_output=True, text=True)


def check_citation_style(pdf):
    """PeerJ's in-text citations carry a comma: "(Clark and Evans, 1954)".

    This was WRONG for the whole life of the PeerJ build and nothing caught it. `main.tex`
    carries \\bibpunct[, ]{(}{)}{;}{a}{}{,}, which OVERRIDES the class and renders the
    comma-LESS form "(Clark and Evans 1954)" -- measured by building a minimal document both
    ways, see convert_to_peerj.py. The converter now deletes that line and lets wlpeerj.cls
    supply its own punctuation.

    The check is on the BUILT PDF, because the style is decided by natbib at typesetting
    time: a `.tex` that looks right can still print the wrong form. A published PeerJ paper
    (peerj-20977) is the reference for "(Author, 2024)". Counts are compared so a single
    stray match cannot decide the verdict.
    """
    txt = subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True,
                         text=True).stdout
    comma = len(re.findall(r"\([A-Z][A-Za-z\-]+(?: et al\.| and [A-Z][A-Za-z\-]+|\b),"
                           r" \d{4}[a-z]?\)", txt))
    nocomma = len(re.findall(r"\([A-Z][A-Za-z\-]+(?: et al\.| and [A-Z][A-Za-z\-]+|\b)"
                             r" \d{4}[a-z]?\)", txt))
    if comma == 0 and nocomma == 0:
        raise SystemExit("REFUSING: no in-text citations found in %s to check" % pdf)
    if nocomma > comma:
        raise SystemExit(
            "REFUSING: %s renders %d comma-less citations against %d with a comma. PeerJ "
            "writes '(Author, 2024)'; a \\bibpunct line in the source will produce the "
            "comma-less form." % (os.path.basename(pdf), nocomma, comma))
    return comma, nocomma


def check_abstract_length(main_tex):
    """The cover page, the portal values and this bundle must state ONE abstract length.

    They disagreed: the cover said 197, `portal-values.md` said 198, and the rendered
    abstract holds 199 words. Each number was computed independently and both were wrong, so
    the check is now a comparison between the documents and the manuscript rather than a
    number typed twice.
    """
    source = os.path.join(PJ, "source")
    if source not in sys.path:
        sys.path.insert(0, source)
    from paper_source import abstract_word_count

    truth = abstract_word_count(main_tex)

    cover = open(os.path.join(PJ, "peerj-cover.tex"), encoding="utf-8").read()
    m = re.search(r"Abstract length\}\\\\\s*(\d+)\s*words", cover)
    if not m:
        raise SystemExit("REFUSING: peerj-cover.tex states no abstract length to check")
    if int(m.group(1)) != truth:
        raise SystemExit("REFUSING: the cover page says %s words, the abstract has %d"
                         % (m.group(1), truth))

    portal = open(os.path.join(PJ, "portal-values.md"), encoding="utf-8").read()
    m = re.search(r"^(\d+) words", portal, re.M)
    if not m:
        raise SystemExit("REFUSING: portal-values.md states no abstract length to check")
    if int(m.group(1)) != truth:
        raise SystemExit("REFUSING: portal-values.md says %s words, the abstract has %d"
                         % (m.group(1), truth))
    return truth


def main():
    # --- freshness: a PDF older than its source means the bundle would ship stale output
    for tex, pdf in (("peerj-main.tex", "peerj-main.pdf"), ("peerj-si.tex", "peerj-si.pdf"),
                     ("peerj-cover.tex", "peerj-cover.pdf")):
        if (not os.path.exists(os.path.join(PJ, pdf))
                or os.path.getmtime(os.path.join(PJ, pdf)) < os.path.getmtime(os.path.join(PJ, tex))):
            raise SystemExit("%s is missing or older than %s: rebuild with pdflatex first" % (pdf, tex))

    # --- every figure the manuscript cites must be shipped, and vice versa
    main_tex = open(os.path.join(PJ, "peerj-main.tex"), encoding="utf-8").read()
    cited = set(re.findall(r"includegraphics\[[^\]]*\]\{([^}]*)\}", main_tex))
    shipped = {f for f in os.listdir(os.path.join(PJ, "figures")) if not f.startswith("Figure")}
    if cited != shipped:
        raise SystemExit("figure mismatch: cited %s, shipped %s" % (sorted(cited), sorted(shipped)))

    # --- the cover page and the portal values must agree with the manuscript on one number
    abstract_words = check_abstract_length(main_tex)

    # --- the built PDF must print peerJ's citation style, not the source's \bibpunct form
    citations = check_citation_style(os.path.join(PJ, "peerj-main.pdf"))

    # --- THE ORDER OF THE "Figure N" NAMES IS THE ORDER THE MANUSCRIPT CITES THEM.
    # This file used to name them from a plain `sorted()` of the source slugs, which is
    # alphabetical, not citation order, so figC0_study_area became "Figure 1" and
    # figC8_tolerance became "Figure 4". The manuscript numbers them the other way round
    # (Fig. 1 is the tolerance figure, Fig. 4 is the study area), so the bundle shipped
    # Figure 1 and Figure 4 swapped against the text a reviewer reads. The mapping is now
    # read from the \includegraphics calls -- the same rule `convert_to_peerj.py` already
    # used -- and is checked against the files that converter wrote before anything is
    # copied, so the two scripts cannot disagree again.
    figure_order = []
    for p in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", main_tex):
        b = os.path.basename(p)
        if b not in figure_order:
            figure_order.append(b)

    def digest(path):
        return hashlib.sha256(open(path, "rb").read()).hexdigest()

    for i, name in enumerate(figure_order, 1):
        n = "Figure %d%s" % (i, os.path.splitext(name)[1])
        src_named = os.path.join(PJ, "figures", n)
        if not os.path.exists(src_named):
            raise SystemExit("REFUSING: %s not found. Run convert_to_peerj.py first." % src_named)
        if digest(src_named) != digest(os.path.join(PJ, "figures", name)):
            raise SystemExit(
                "REFUSING: figures/%s is not %s. The converter and this script disagree "
                "about the figure order." % (n, name))

    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, "figures"))
    os.makedirs(os.path.join(OUT, "latex_source"))

    report = ["PeerJ bundle built %s" % DAY, ""]
    for pdf, portal_name in UPLOADS.items():
        shutil.copy2(os.path.join(PJ, pdf), os.path.join(OUT, portal_name))
        log = os.path.join(PJ, pdf.replace(".pdf", ".log"))
        txt = open(log, errors="replace").read() if os.path.exists(log) else ""
        pages = re.search(r"Output written on \S+ \((\d+) page", txt)
        report.append("%-34s errors=%d  undefined=%d  overfull=%d  pages=%s"
                      % (portal_name, len(re.findall(r"(?m)^!", txt)),
                         len(re.findall(r"(?i)undefined", txt)),
                         txt.count("Overfull"), pages.group(1) if pages else "?"))
        report.append("    sha256 %s" % hashlib.sha256(
            open(os.path.join(OUT, portal_name), "rb").read()).hexdigest())

    for f in sorted(shipped):
        shutil.copy2(os.path.join(PJ, "figures", f), os.path.join(OUT, "figures", f))
    # Copy the "Figure N" files the converter wrote rather than making new names here: the
    # converter owns the numbering (it reads citation order), this script only ships it.
    for i, name in enumerate(figure_order, 1):
        ext = os.path.splitext(name)[1]
        out_name = "Figure %d%s" % (i, ext)
        shutil.copy2(os.path.join(PJ, "figures", out_name),
                     os.path.join(OUT, "figures", out_name))
    report.append("")
    report.append("abstract: %d words (cover page, portal-values.md and this file all agree)"
                  % abstract_words)
    report.append("citations: %d with a comma, %d without (PeerJ writes \"(Author, 2024)\")"
                  % citations)
    report.append("figures: %d, each uploaded separately under \"Figure N\" (order = citation "
                  "order in the manuscript)" % len(figure_order))
    for i, name in enumerate(figure_order, 1):
        report.append("    Figure %d.pdf <- %s" % (i, name))

    for f in SOURCES:
        shutil.copy2(os.path.join(PJ, f), os.path.join(OUT, "latex_source", f))
    # `wlpeerj.cls` is the one file in this bundle whose type PeerJ does not name in either
    # list. PeerJ's rule for an unnamed type: "For other file types, please upload a zip file
    # containing the file you want to upload." Wrapping all five sources in one archive is
    # the form that is correct regardless, and it keeps the source set together.
    tex_zip = os.path.join(OUT, "latex_source.zip")
    with zipfile.ZipFile(tex_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for f in SOURCES:
            z.write(os.path.join(PJ, f), f)
    shutil.copy2(os.path.join(PJ, "portal-values.md"),
                 os.path.join(OUT, "portal-values.md"))
    # The portal's Title / Short Title / Abstract are plain-text fields with their own
    # character limits (250 / 50 / 2000 CHARACTERS), and the checklist warns about linebreaks
    # and special characters in them. They are extracted from the built PDF by
    # source/make_portal_fields.py so they cannot drift from the manuscript.
    for extra in ("portal-fields.md",):
        p = os.path.join(PJ, extra)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(OUT, extra))
        else:
            raise SystemExit("REFUSING: %s missing. Run source/make_portal_fields.py." % extra)

    open(os.path.join(OUT, "START_HERE.md"), "w", encoding="utf-8").write(START.format(day=DAY))
    open(os.path.join(OUT, "build-report.txt"), "w", encoding="utf-8").write("\n".join(report) + "\n")

    sums = []
    for root, _, files in os.walk(OUT):
        for f in sorted(files):
            p = os.path.join(root, f)
            rel = os.path.relpath(p, OUT)
            if rel == "SHA256SUMS.txt":
                continue
            sums.append("%s  %s" % (hashlib.sha256(open(p, "rb").read()).hexdigest(), rel))
    open(os.path.join(OUT, "SHA256SUMS.txt"), "w", encoding="utf-8").write("\n".join(sums) + "\n")

    zip_path = os.path.join(PJ, "dist", NAME + ".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(OUT):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.join(NAME, os.path.relpath(p, OUT)))
    print("\n".join(report))
    print("\n%s  (%.1f MB)" % (zip_path, os.path.getsize(zip_path) / 1e6))


if __name__ == "__main__":
    main()
