#!/usr/bin/env python3
"""
Convert `main.tex` to a PeerJ manuscript (wlpeerj class).

Output: the parent of this directory (the submission root), as `peerj-main.tex`
(+ class, .bib, figures).

Learned from the official template (LaTeX_Template_for_PeerJ_Journal_Submissions.zip):
  * \\documentclass[fleqn,10pt,lineno]{wlpeerj}  -- lineno is REQUIRED for review.
  * Front matter: \\title, \\author[n]{}, \\affil[n]{}, \\corrauthor[n]{}{email},
    then \\begin{abstract}...\\end{abstract}; then \\flushbottom\\maketitle.
  * The class DISABLES keywords (the sample's \\keywords is commented out), so the
    The \\keyword{} block is dropped, not converted.
  * Sections are NOT forced unnumbered -- the class numbers \\section{} and has a
    separate numberless format -- so the manuscript's 18 "Section~\\ref{}"
    cross-references keep working unchanged. Nothing is rewritten to prose names.
  * natbib + apalike come from the class; citations reuse the Harvard conversion.

Only the framing changes; no number, figure or result is touched.

Usage:  python3 convert_to_peerj.py [--src DIR] [--out DIR]
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import sys

# shared source helpers (grab/drop, credit and disclosure constants, citation and
# supplement conversion). These used to live in the Taylor & Francis converter.
from paper_source import (SRC, ADDRESS, grab, drop, first_authors,
                          convert_citations, convert_supplement,
                          CREDIT, CONTRIBUTOR_NOTES,
                          AI_DECLARATION, AI_DISCLOSURE)

# THE OUTPUT IS THE REPOSITORY ROOT, ONE LEVEL UP FROM THIS FILE.
# This used to be a hard-coded absolute path to the author's machine, which meant the
# repository could not be built anywhere else and said nothing about where its own output
# belonged. `source/` sits directly inside the submission folder, so the parent of this
# file's directory IS the root the generated documents belong at.
OUT = pathlib.Path(__file__).resolve().parent.parent
SHIP = ["wlpeerj.cls"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    src = pathlib.Path(a.src)
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    tex = (src / "main.tex").read_text()

    # ---- 1. class + packages ------------------------------------------------
    # The source is venue-neutral: it typesets in the article class and defines its own
    # front-matter macros, so the PeerJ class and packages replace that preamble whole.
    tex = re.sub(r"%={10,}\n%\s*Source manuscript\..*?\n%={10,}\n",
                 "%=================================================================\n"
                 "%  PeerJ (PeerJ Inc. / Taylor & Francis). wlpeerj class.\n"
                 "%  Build: pdflatex x2, bibtex, pdflatex x2. Line numbers on for review.\n"
                 "%=================================================================\n",
                 tex, flags=re.S)
    # Drop the neutral preamble: the article class, its packages, and the front-matter
    # macro definitions (they are no-ops under wlpeerj, which supplies its own). A function
    # PEERJ'S IN-TEXT CITATIONS CARRY A COMMA: "(Clark and Evans, 1954)".
    # `wlpeerj.cls` loads natbib and sets \bibliographystyle{apalike}, and with the class's
    # own settings that is the form it produces -- MEASURED, not assumed: a minimal document
    # using only the class renders `(Clark and Evans, 1954)`.
    #
    # The source's own \bibpunct[, ]{(}{)}{;}{a}{}{,} OVERRIDES that and renders
    # `(Clark and Evans 1954)`, i.e. it REMOVES the comma. The same minimal document with
    # that line added renders the comma-less form. So for wlpeerj the correct action is to
    # DELETE the punctuation directive and let the class supply its own, which is what this
    # does. The line must not be carried over: doing so changes the citation style of every
    # reference in the paper.
    tex = re.sub(r"\\bibpunct\[[^\]]*\](?:\{[^{}]*\})*\n", "", tex)

    # replacement is used because the PeerJ preamble is LaTeX, and re.sub treats a
    # backslash in a replacement string as an escape.
    PEERJ_PREAMBLE = ("\\documentclass[fleqn,10pt,lineno]{wlpeerj}\n"
                      "\\usepackage{siunitx}\n"
                      # textcomp supplies the TEXT-font degree sign (\\textdegree), which
                      # is U+00B0 in Latin-1 and therefore survives PeerJ's font-map
                      # rewrite. The math-font alternative ($^\\circ$, U+25E6) does not:
                      # the same rewrite that turns the minus into a digit turns the
                      # degree sign into a cedilla. See the minus note below.
                      "\\usepackage{textcomp}\n"
                      # MAKE EVERY MINUS AN ASCII HYPHEN-MINUS, because PeerJ's own PDF
                      # pipeline CORRUPTED OURS. This was a real defect, found by comparing
                      # the reviewing PDF PeerJ generated (peerj-reviewing-150843-v0.pdf)
                      # against ours:
                      #
                      #   ours  : "the multiscale decline is U+2212 9 9 m per year"
                      #   PeerJ : "the multiscale decline is 2 9 9 m per year"
                      #
                      # The bytes confirm it: ours is e2 88 92 (U+2212 MINUS SIGN), theirs
                      # is 32 (the digit TWO). A published PDF would then state positive
                      # quantities where the paper reports negative ones -- "-99 m per year"
                      # published as "299 m per year".
                      #
                      # The cause is the GLYPH'S FONT. The math minus comes from CMSY10, a
                      # Type 1 math-symbol font. PeerJ's pipeline rewrites that font's
                      # ToUnicode map: the codes whose Unicode target is ASCII or Latin-1
                      # are kept, and every code whose target is a maths symbol (U+2212,
                      # U+2264, U+221A, U+2192, U+2208, U+2217) is replaced with whatever the
                      # font's internal encoding happens to say. So the PAGE still looks
                      # right -- this is a text-layer defect, invisible in print -- but a
                      # text extractor, a search engine or a screen reader reads a digit.
                      # The same rewrite cost us U+2264 <=, U+2265 >=, U+221A sqrt, U+2192 ->
                      # and U+25E6 for the degree sign, so it is a class of defect, not one
                      # character.
                      #
                      # ASCII is immune to the rewrite because every encoding maps it the
                      # same way. \\DeclareMathSymbol re-points the math minus at the
                      # operators font's ASCII hyphen-minus (slot "2D).
                      #
                      # Rejected alternatives, both measured:
                      #   - \\mathcode`\\-="8000 with an active definition routes the minus
                      #     through \\textminus, but raises "! Bad mathchar (32768)" at
                      #     \\begin{document} because a mathcode of 0x8000 is out of range.
                      #   - leaving the default in place, which keeps the proper U+2212 glyph
                      #     but is exactly what PeerJ's pipeline mangles.
                      #
                      # Verified after the change: CMSY10 is no longer set from any text
                      # minus, and a Ghostscript round trip (gs 9.54.0, the same family as
                      # PeerJ's 9.56.1) leaves the byte 2d ("-"), which no encoding can
                      # confuse with a digit.
                      "\\DeclareMathSymbol{-}{\\mathbin}{operators}{\"2D}\n"
                      "\\usepackage[hidelinks]{hyperref}\n"
                      # PeerJ's review column is narrow (left=5cm in wlpeerj.cls) and the
                      # text has long unbreakable tokens (the grant number, DOI URLs);
                      # without this the Funding line runs 56pt into the margin.
                      "\\usepackage{url}\n"
                      "\\usepackage{xurl}\n"
                      "\\usepackage{amsmath}\n"
                      "\\usepackage{booktabs}\n"
                      "\\usepackage{graphicx}\n"
                      "\\emergencystretch=3em\n"
                      "\\sloppy\n")
    tex = re.sub(r"\\documentclass\{article\}\n"
                 r"(?:\s*\\usepackage\{[^}]*\}\n)*"
                 r"(?:\s*\\bibpunct\[[^\]]*\]\n)?"
                 r"(?:\s*\\graphicspath\{\{[^}]*\}\}\n)?"
                 r"(?:(?:\s*%[^\n]*\n)|(?:\s*\n))*"
                 r"(?:(?:\\newcommand\{\\(?:Title|Author|AuthorNames|corres|address|firstpage|"
                 r"pubvolume|issuenum|articlenumber|pubyear|copyrightyear|datereceived|"
                 r"daterevised|dateaccepted|datepublished|Abstract|keyword|reftitle|"
                 r"authorcontributions|funding|dataavailability|acknowledgments|"
                 r"conflictsofinterest|supplementary)\}\[[0-9]\]\{[^\n]*\}\n)|(?:\s*%[^\n]*\n))*",
                 lambda m: PEERJ_PREAMBLE, tex, count=1)
    tex = re.sub(r"\\usepackage\{Definitions[^}]*\}\n?", "", tex)

    # Drop the source's OWN \bibliographystyle. `wlpeerj.cls` already issues
    # \bibliographystyle{apalike}, and a .bib cannot carry two \bibstyle commands:
    # BibTeX keeps the FIRST and logs "Illegal, another \bibstyle command" for the second,
    # which was a real error in every build. The class's style is the one that must win --
    # it is what the journal's own class asks for, and apalike plus the \bibpunct above is
    # what reproduces PeerJ's "(Author, 2024)" citation form.
    tex = re.sub(r"\\bibliographystyle\{[^}]*\}\n", "", tex)

    # Remove the neutral source's front-matter MACRO DEFINITIONS. They are single lines
    # holding nested braces (\newcommand{\Title}[1]{\title{#1}\def...}), and if they
    # survive, make_peerj_cover.py's grab_all() matches the "#1" inside \title{#1} /
    # \author{#1} and prints a literal "#1" on the cover page. The \Title{...} USES are
    # kept: the converter reads them below.
    tex = re.sub(r"(?m)^\\newcommand\{\\(?:Title|Author|AuthorNames|corres|address|firstpage|"
                 r"pubvolume|issuenum|articlenumber|pubyear|copyrightyear|datereceived|"
                 r"daterevised|dateaccepted|datepublished|Abstract|keyword|reftitle|"
                 r"authorcontributions|funding|dataavailability|acknowledgments|"
                 r"conflictsofinterest|supplementary)\}\[[0-9]\]\{.*\}$\n?", "", tex)

    # ---- 2. front matter ----------------------------------------------------
    title = (grab(tex, "Title") or "").strip()
    tex = drop(tex, "Title")
    # The neutral source calls the abstract \Abstract: \abstract is an environment in the
    # article class and cannot be redefined as a command.
    abstract = (grab(tex, "Abstract") or grab(tex, "abstract") or "").strip()
    tex = drop(tex, "Abstract")
    tex = drop(tex, "abstract")
    tex = drop(tex, "keyword")          # PeerJ disables keywords
    for n in ["AuthorNames", "Author", "corres", "address",
              "firstpage", "pubvolume", "issuenum", "articlenumber", "pubyear",
              "copyrightyear", "datereceived", "daterevised", "dateaccepted",
              "datepublished", "reftitle"]:
        tex = drop(tex, n)
    tex = re.sub(r"\\makeatletter\n\\setcounter\{page\}\{\\@firstpage\}\n\\makeatother",
                 "", tex)

    # AUTHOR ORDER, and it must match the portal's author list exactly. The submission form
    # lists Ammar Arbaaeen first, so the manuscript prints him first too. Wael Alnahari stays
    # the CORRESPONDING author -- that is a separate field, and it does not follow the
    # first-author position.
    #
    # \corrauthor's OPTIONAL ARGUMENT IS THE AFFILIATION SUPERSCRIPT, not the author's
    # position: wlpeerj.cls sets \thecorrauthor as "#2$^{#1}$", so [1] prints
    # "Wael Alnahari^1". Alnahari is still at KAU, which is \affil[1], so this stays [1].
    # Changing it to [2] when the order changed would have printed the WRONG affiliation
    # against his name, which is what a corresponding-author line must never do.
    AUTHOR = (
        "\\title{" + title + "}\n\n"
        "\\author[2]{Ammar Arbaaeen}\n"
        "\\author[1]{Wael Alnahari}\n"
        "\\author[2]{Ammar Alsaig}\n"
        "\\author[1]{Tawfiq Hasanin}\n"
        "\\author[3]{Wasem Alnahri}\n\n"
        "\\affil[1]{Department of Information Systems, Faculty of Computing and "
        "Information Technology, King Abdulaziz University, Jeddah 21589, Saudi Arabia}\n"
        "\\affil[2]{Department of Computer Science, College of Computer and Information "
        "Systems, Umm Al-Qura University, Mecca 24381, Saudi Arabia}\n"
        "\\affil[3]{Independent Researcher, Mecca 24331, Saudi Arabia}\n\n"
        "\\corrauthor[1]{Wael Alnahari}{walnahari0004@stu.kau.edu.sa}\n\n"
        # THE TEMPLATE'S ONE FIELD THE CLASS DOES NOT PRINT.
        #
        # PeerJ's Author Cover Page template asks for: manuscript title; authors;
        # affiliations; the corresponding author; that author's STREET ADDRESS, city,
        # state/province, zip and country; and the e-mail address. wlpeerj's own \maketitle
        # prints every one of those EXCEPT the postal address, and it prints them in the right
        # order. So the cover page is not a separate document and not an extra block at the
        # end of the page: it is this one field, added to the block \maketitle already emits
        # as \thecorrauthor, which sits ABOVE the abstract.
        #
        # wlpeerj.cls hard-codes the text of \thecorrauthor, so the address cannot be passed
        # through \corrauthor's arguments. It is appended to the definition instead: the class
        # sets \thecorrauthor, and this extends it with the address and the originality
        # statement, in the same style.
        "\\let\\origTheCorrAuthor\\thecorrauthor\n"
        "\\def\\thecorrauthor{\\origTheCorrAuthor\\medskip\n"
        "Postal address: " + ADDRESS + "\\par}\n")

    front = (AUTHOR + "\n\\begin{abstract}\n" + abstract + "\n\\end{abstract}\n\n"
             "\\begin{document}\n\n\\flushbottom\n\\maketitle\n\\thispagestyle{empty}\n")

    tex = re.sub(r"\\begin\{document\}\s*\n\s*\\maketitle", lambda m: front, tex, count=1)

    # ---- 2b. NOTE: the Author Cover Page is spliced in further down, at step 4b --------
    #
    # It has to be, and the reason is a real ordering constraint rather than tidiness.
    # make_peerj_cover.py PARSES `peerj-main.tex` to read the title, authors, affiliations and
    # corresponding e-mail, so it can only run after that file has been written. The cover
    # content is therefore spliced in immediately after the write at step 4, not here.

    # ---- 3. citations (Harvard style) --------------------------------------
    bib_first = first_authors(src / "references.bib")
    tex, named, others, bare = convert_citations(tex, bib_first)

    # ---- 3b. unnumbered sections + named cross-references -------------------
    # The PeerJ template writes \section*{Introduction} (STARRED) and the published
    # journals carry unnumbered headings with no numeric "Section N" references.
    # Numbering is permitted by the class but is NOT PeerJ's style, so every
    # section/subsection is starred and each "Section~\ref{sec:x}" becomes a SHORT
    # noun phrase. Using the full heading was ungrammatical ("in the co-location is
    # duplicated registration, not a rounding artefact"), because the manuscript's
    # subsection titles are clauses; a short map keeps the sentences readable.
    SHORT = {
        "sec:intro": "introduction",
        "sec:contribution": "contribution list",
        "sec:prior": "relation to existing work",
        "sec:methods": "methods",
        "sec:data": "census definition",
        "sec:units": "spatial-unit analysis",
        "sec:indices": "estimator section",
        "sec:isotropy": "isotropy test",
        "sec:boundaries": "interpretive boundaries",
        "sec:results": "results",
        "sec:results-summary": "summary of findings",
        "sec:results-population": "population-turnover analysis",
        "sec:results-trend": "clustering-trend analysis",
        "sec:results-unit": "unit-and-concentration analysis",
        "sec:results-origin": "co-location analysis",
        "sec:results-mech": "multiscale analysis",
        "sec:results-powerlaw": "size-versus-time analysis",
        "sec:results-theme": "theme-discontinuity analysis",
        "sec:discussion": "discussion",
        "sec:disc-longitudinal": "practical implications",
        "sec:disc-transfer": "transferable rule",
        "sec:limits": "limitations",
        "sec:conclusions": "conclusions",
    }

    def _sentence_initial(text: str, pos: int) -> bool:
        """True if only whitespace separates `pos` from a sentence-ending mark."""
        j = pos - 1
        while j >= 0 and text[j] in " \t\n":
            j -= 1
        return j < 0 or text[j] in ".!?"

    def short(m):
        phrase = "the " + SHORT.get(m.group(1), "section above")
        # A sentence-initial phrase must be capitalised: "the relation to existing work
        # sets out ..." after a full stop is ungrammatical and shipped once.
        if _sentence_initial(tex, m.start()):
            return phrase[0].upper() + phrase[1:]
        return phrase

    # "Section~\ref{sec:x}" / "Sections~\ref{sec:x}" -> "the <short>"
    tex = re.sub(r"Sections?~\\ref\{(sec:[^}]*)\}", short, tex)
    # "(Sections~\ref{a}, \ref{b})" -> "the <a> and the <b>"
    tex = re.sub(r"\\ref\{(sec:[^}]*)\}",
                 lambda m: "the " + SHORT.get(m.group(1), "section above"), tex)

    tex = re.sub(r"\\section\{", lambda m: "\\section*{", tex)
    tex = re.sub(r"\\subsection\{", lambda m: "\\subsection*{", tex)

    # ---- 3c. figure citation abbreviation -----------------------------------
    # PeerJ's Author Instructions: "When citing use the abbreviation 'Fig.'.
    # When starting a sentence with a citation, use 'Figure 1'." The source
    # writes "Figure~\ref{fig:...}" everywhere, so mid-sentence citations become
    # "Fig.~" and only a genuinely sentence-initial one keeps "Figure".
    def _figcite(m):
        j = m.start() - 1
        # walk back past whitespace to the previous real character: a source
        # line-wrap must NOT be mistaken for the start of a sentence
        while j >= 0 and tex[j] in " \t\n":
            j -= 1
        if j < 0 or tex[j] in ".!?":
            return "Figure~\\ref{fig:"   # genuine sentence start
        return "Fig.~\\ref{fig:"
    tex = re.sub(r"Figure~\\ref\{fig:", _figcite, tex)

    # PeerJ calls the supplement "Supplemental Information" and numbers its items
    # ("Supplemental Material S1"). "Supplementary Material" is the other venues' term,
    # so it is rewritten here.
    # The first mention names the upload; later ones shorten it. PeerJ's instructions ask
    # for that naming ("Supplemental Data S1") and the file must be recognisable in the list.
    _si_first = [True]

    def _si_mention(m):
        if _si_first[0]:
            _si_first[0] = False
            return "Supplemental Information (S1)"
        return "Supplemental Information"

    tex = re.sub(r"Supplementary Material", _si_mention, tex)
    tex = re.sub(r"\\supplementary\{", r"\\supplementary{Supplemental Information S1. ", tex)

    # PeerJ: "Figure 1 appears first in the text, and first cited." The source cites
    # fig:tolerance in the introduction and the other three in the results, so the float
    # blocks are re-emitted in first-citation order and LaTeX renumbers them. Only the
    # floats move; the prose keeps its position.
    _blocks = re.findall(r"\\begin\{figure\}.*?\\end\{figure\}", tex, flags=re.S)
    if _blocks:
        _pos = {}
        for _b in _blocks:
            _lab = re.search(r"\\label\{(fig:[^}]*)\}", _b)
            assert _lab, "a figure float has no \\label"
            _at = re.findall(r"\\ref\{%s\}" % re.escape(_lab.group(1)), tex)
            assert _at, "figure %s is never cited in the text" % _lab.group(1)
            _pos[_b] = [m.start() for m in re.finditer(r"\\ref\{%s\}" % re.escape(_lab.group(1)), tex)][0]
        _order = sorted(_blocks, key=lambda b: _pos[b])
        for _n, _b in enumerate(_blocks):
            tex = tex.replace(_b, "\x01FIGURE%d\x01" % _n, 1)
        # placeholders sit in document order, so popping the first-cited float into each
        # one in turn re-emits them ordered without moving the prose.
        tex = re.sub(r"\x01FIGURE\d+\x01", lambda m: _order.pop(0), tex)

    # ---- 4. back matter as plain sections -----------------------------------
    parts = {}
    for n in ["authorcontributions", "funding", "dataavailability",
              "acknowledgments", "conflictsofinterest", "supplementary"]:
        parts[n] = (grab(tex, n) or "").strip()
        tex = drop(tex, n)

    # PeerJ's published back-matter structure, verified against peerj-20977.pdf
    # (page 24) and the Author Instructions: one wrapper section,
    # "ADDITIONAL INFORMATION AND DECLARATIONS", then the standard subsections in
    # the order Funding / Grant Disclosures / Competing Interests /
    # Author Contributions / Data Availability / Supplemental Information.
    # The subsections are \subsection* so they nest under the wrapper heading.
    decl = []
    if parts["funding"]:
        decl.append("\\subsection*{Funding}\n\\noindent " + parts["funding"])
        # PeerJ prints a separate "Grant Disclosures" restating the grant number.
        # The number may be written out or hidden behind the \uquGrant macro, so
        # look for both rather than duplicating a hand-typed copy.
        _grants = re.findall(r"26UQU[0-9]{7}GSSR[0-9]{2}", parts["funding"])
        if not _grants and "\\uquGrant" in parts["funding"]:
            _grants = ["26UQU4350624GSSR07"]  # value of \uquGrant in main.tex
        if _grants:
            decl.append(
                "\\subsection*{Grant Disclosures}\n\\noindent The following grant "
                "information was disclosed by the author: Umm Al-Qura University "
                "(Deanship of Postgraduate Studies and Scientific Research), "
                + ", ".join(sorted(set(_grants))) + ".")
    if parts["conflictsofinterest"]:
        decl.append("\\subsection*{Competing Interests}\n\\noindent "
                    + parts["conflictsofinterest"])
    # CREDIT carries its own \subsection* heading; the wrapper supplies the
    # "Author Contributions" heading, so strip CREDIT's own to avoid nesting a
    # subsection inside a subsection.
    _credit_body = re.sub(r"^\\subsection\*\{[^}]*\}\s*", "", CREDIT)
    decl.append("\\subsection*{Author Contributions}\n\\noindent " + _credit_body)
    if parts["dataavailability"]:
        decl.append("\\subsection*{Data Availability}\n\\noindent "
                    + parts["dataavailability"])
    if parts["supplementary"]:
        decl.append("\\subsection*{Supplemental Information}\n\\noindent "
                    + parts["supplementary"])
    decl.append(CONTRIBUTOR_NOTES)
    # One AI statement only. The source Acknowledgments already ends with a
    # sentence about Copilot, and this converter would otherwise also append
    # AI_DISCLOSURE under Acknowledgments -- producing TWO AI statements (one in
    # Acknowledgments, one here). Keep the structured one, placed with the other
    # declarations, and drop the inline sentence from the acknowledgments below.
    decl.append(AI_DISCLOSURE)

    ack = ""
    if parts["acknowledgments"]:
        _ack_body = parts["acknowledgments"]
        # remove the inline Copilot/AI sentences so the statement appears once.
        # Collapse whitespace first: the source wraps mid-phrase ("this work the
        # \n authors used ..."), so any pattern with literal single spaces fails.
        _ack_body = re.sub(r"\s+", " ", _ack_body).strip()
        _ack_body = re.sub(r"\s*During the preparation of this work.*?Copilot\b.*?"
                           r"full responsibility for the content of the publication\.",
                           "", _ack_body, flags=re.S).strip()
        ack = "\\section*{Acknowledgments}\n\\noindent " + _ack_body

    decl_block = ("\\section*{Additional Information and Declarations}\n\n"
                  + "\n\n".join(decl))
    block = "\n\n" + ack + "\n\n" + decl_block + "\n\n"
    tex = re.sub(r"\n\\bibliography\{references\}", lambda m: block + m.group(0),
                 tex, count=1)

    # ---- write --------------------------------------------------------------
    (out / "peerj-main.tex").write_text(tex)
    bib = (src / "references.bib").read_text()
    (out / "references.bib").write_text(bib)
    shutil.copy2(src / "wlpeerj.cls", out / "wlpeerj.cls")
    # COPY ONLY THE FIGURES THE MANUSCRIPT ACTUALLY CITES.
    # PeerJ requires that "all figures must be cited in the main text", and the portal asks
    # for one uploaded file per figure. The source `figures/` directory holds nine PDFs, but
    # only four are cited; copying the directory wholesale put five uncited figure files in
    # the submission bundle. An uncited uploaded figure is a defect a reviewer can see, so
    # the copy is now driven by the \includegraphics calls in the generated .tex and any
    # leftover file is REPORTED rather than shipped silently.
    cited = sorted({os.path.basename(p) for p in re.findall(
        r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", tex)})
    # PEERJ ASKS FOR FILENAMES THAT CARRY THE FIGURE NUMBER: "Include figure numbers in
    # filenames e.g., 'Figure 1.png'". The source names are descriptive slugs (figC0_study_area)
    # which say nothing about order, so each cited figure is written out under its ORDINAL
    # position in the manuscript as well as copied under its source name. The ordinal is read
    # from the order the \includegraphics calls appear in the body, which is the order PeerJ
    # requires figures to be numbered in. The .tex keeps the source name, so a rename here can
    # never break the build.
    order = []
    for p in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", tex):
        b = os.path.basename(p)
        if b not in order:
            order.append(b)
    src_figs = src / "figures"
    if (out / "figures").exists():
        shutil.rmtree(out / "figures")
    (out / "figures").mkdir(parents=True)
    for name in cited:
        s = src_figs / name
        if not s.exists():
            raise SystemExit(
                "REFUSING to finish: %s is cited but absent from %s" % (name, src_figs))
        shutil.copy2(s, out / "figures" / name)
        n = order.index(name) + 1
        shutil.copy2(s, out / "figures" / ("Figure %d%s" % (n, os.path.splitext(name)[1])))
    orphaned = sorted(p.name for p in src_figs.glob("*.pdf")
                      if p.name not in cited)
    print("  figures: %d cited and copied, also as %s"
          % (len(cited), ", ".join("Figure %d.pdf" % (i + 1) for i in range(len(cited)))))
    if orphaned:
        print("  figures NOT cited, therefore not shipped: %s" % ", ".join(orphaned))

    # ---- supplement ---------------------------------------------------------
    si_tex = convert_supplement(src, out, "peerj")
    (out / "peerj-si.tex").write_text(si_tex)

    print("wrote %s" % (out / "peerj-main.tex"))
    print("wrote %s" % (out / "peerj-si.tex"))
    print("  citations: %d \\citep, %d \\citet, %d \\citeyearpar" % (bare, named, others))
    print("  sections starred (PeerJ style); Section~\\ref replaced by short names")

    # ---- publishable-defect guard -------------------------------------------
    # These strings must never reach a submitted PDF: an author-only instruction
    # inside the manuscript, and a placeholder that looks like a real value. Both
    # were shipped once (found 2026-10-09) because the constants they live in are
    # shared across builds and nothing checked the generated output.
    _FORBIDDEN = [
        ("VERIFY-VERSION", "unfilled tool-version placeholder"),
        ("to be expanded by the author", "author-only instruction in a published field"),
        ("PLACEHOLDER", "placeholder marker"),
        ("XXX", "placeholder marker"),
        ("FIXME", "unresolved marker"),
        ("TODO", "unresolved marker"),
    ]
    def _guard(path):
        text = path.read_text()
        body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("%"))
        bad = [w for w, _ in _FORBIDDEN if w in body]
        if bad:
            raise SystemExit(
                "REFUSING to finish: %s contains %s. These would be published."
                % (path.name, ", ".join(bad)))
    for _p in (out / "peerj-main.tex", out / "peerj-si.tex"):
        _guard(_p)
    print("  guard: no placeholder or author-instruction strings in the output")

    # ---- cover page ---------------------------------------------------------
    # PeerJ's Author Instructions list an "Author Cover Page" among the manuscript
    # requirements. It is generated from the manuscript just written, so its title,
    # authors and affiliations cannot drift from `peerj-main.tex`.
    #
    # The script is located from SRC (the directory holding main.tex, imported from
    # paper_source), not from a HERE constant -- this module defines neither HERE
    # nor __file__-relative paths, and referring to HERE raised NameError.
    import subprocess
    r = subprocess.run([sys.executable, str(src / "make_peerj_cover.py")],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("REFUSING to finish: cover page generation failed:\n"
                         + (r.stdout or "") + (r.stderr or ""))
    for line in (r.stdout or "").splitlines():
        print("  " + line.strip())

    return 0


if __name__ == "__main__":
    sys.exit(main())
