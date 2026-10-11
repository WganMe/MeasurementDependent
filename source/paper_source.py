#!/usr/bin/env python3
"""Shared source helpers for the PeerJ build.

Only the helpers the PeerJ build uses live here. The withdrawal of the other
venues removed their converters from this tree.
"""
from __future__ import annotations

import pathlib
import re

# The manuscript sources live beside this module.
SRC = pathlib.Path(__file__).resolve().parent

# The corresponding author's postal address, as PeerJ's template requires (street, city,
# state/province, zip, country). SUPPLIED BY THE AUTHOR, in the Saudi National Address order:
# building number, street, district, city, postcode, country.
#
# The author supplied it as:
#   حي, MDFA3058, 3058 شارع الأمير ناصر بن عبد العزيز آل سعود, 6199, King Fahd, Makkah 24342
#
# The street name is transliterated ONLY, and the Arabic is deliberately NOT carried into the
# .tex: this document is typeset with pdfLaTeX, which cannot set Arabic without a further
# package and an Arabic-capable font, and the build's own guard refuses any non-ASCII byte in
# the generated source. The prince's name renders in English as "Nasser bin Abdulaziz Al Saud"
# (Wikipedia), giving "Prince Nasser bin Abdulaziz Street".
#
# "Makkah" and "MDFA3058" are kept exactly as the author wrote them rather than anglicised to
# "Mecca" or reformatted, because a postal address has to match what the postal service prints.
# If an Arabic line is wanted in the PDF, it needs \\usepackage{arabtex} or a XeLaTeX build,
# which is a different change to the build, not a different string.
ADDRESS = ("MDFA3058, 3058 Prince Nasser bin Abdulaziz Street, King Fahd District, "
           "Makkah 24342, Saudi Arabia")

CREDIT = (
    "\\subsection*{CRediT authorship contribution statement}\n\\noindent "
    "Wael Alnahari: Conceptualization, Methodology, Software, Validation, Formal analysis, "
    "Data curation, Writing -- original draft, Writing -- review and editing, Visualization, "
    "Project administration. Tawfiq Hasanin: Validation, Writing -- review and editing. "
    "Ammar Arbaaeen: Funding acquisition, Writing -- review and editing. Ammar Alsaig: "
    "Writing -- review and editing. Wasem Alnahri: Conceptualization, Validation, "
    "Writing -- review and editing.")

CONTRIBUTOR_NOTES = (
    "\\subsection*{Notes on contributors}\n\\noindent "
    "\\textbf{Wael Alnahari} is in the Department of Information Systems, Faculty of Computing "
    "and Information Technology, King Abdulaziz University, Saudi Arabia. "
    "\\textbf{Ammar Arbaaeen} and \\textbf{Ammar Alsaig} are in the Department of Computer "
    "Science, College of Computer and Information Systems, Umm Al-Qura University, Saudi Arabia. "
    "\\textbf{Tawfiq Hasanin} is in the Department of Information Systems, King Abdulaziz "
    "University, Saudi Arabia. \\textbf{Wasem Alnahri} is an independent researcher, Saudi "
    "Arabia.")

AI_DECLARATION = (
    "\\subsection*{Declaration of generative AI use}\n\\noindent "
    "During the preparation of this work the authors used a generative AI coding assistant to "
    "support LaTeX preparation and language editing. Generative AI was not used to generate or "
    "alter any result, and no AI tool is an author. The authors reviewed and edited all content "
    "and take full responsibility for the publication.")

# WHAT PEERJ REQUIRES, AND WHY THIS STRING IS SHAPED THIS WAY.
# PeerJ's Generative AI policy permits AI-assisted copyediting and language refinement but
# requires the declaration to carry FOUR elements. Quoted from the policy:
#   (a) "originality and accuracy of content has been confirmed by the authors"
#   (b) "the name and version number of the AI tool used"
#   (c) "confirmation the authors have checked terms of use for the specific AI tool used,
#        and therefore confirm suitability for publication"
#   (d) "confirmation the authors take full responsibility for the integrity of the whole
#        content, including accuracy of references"
# The earlier text carried only (b) plus a description of use, so a reviewer checking the
# declaration against the policy would have found three of the four required statements
# missing. They are now each present and separately identifiable.
AI_DISCLOSURE = (
    "\\subsection*{Generative AI Use Disclosure Statement}\n\\noindent "
    "\\textbf{Tool and version.} Tool: GitHub Copilot, version 0.69.0. "
    "\\textbf{How it was used.} Drafting and editing LaTeX and typesetting support. "
    "\\textbf{Reason for use.} Assistance with manuscript preparation and language. "
    "It was not used to compute, alter or select any result; every number in the manuscript is "
    "read from a committed results file produced by the analysis scripts in the deposit. "
    "\\textbf{Originality and accuracy.} The authors confirm the originality and accuracy of "
    "the content. "
    "\\textbf{Terms of use.} The authors have checked the terms of use for this tool and "
    "confirm its use is suitable for publication. "
    "\\textbf{Responsibility.} The authors take full responsibility for the integrity of the "
    "whole content, including the accuracy of all references.")


def abstract_word_count(tex: str) -> int:
    """Count the words of \\begin{abstract}...\\end{abstract} as a reader would read them.

    WHY THIS IS ONE FUNCTION. The cover page and `portal-values.md` each stated a length for
    this abstract and they disagreed (197 and 198), while the rendered PDF holds 199 words, so
    neither number was correct. The count is needed in two places, so it is defined once here
    and imported by both, instead of being derived twice and drifting.

    Macros that stand for plain text are expanded rather than deleted, because deleting
    `\\rDrop` turns "falls 67% on" into "falls on" and loses the number from the count. `\\num`
    and `\\SI` keep their first argument for the same reason: `\\SI{25}{\\meter}` reads as
    "25 m". Command names that are pure formatting (`\\emph`, `\\textbf`) contribute nothing.
    """
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.S)
    if not m:
        return 0
    body = re.sub(r"(?<!\\)%.*", " ", m.group(1))

    # our own \newcommand values are literal text: expand them like \num
    macros = dict(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}\{([^{}]*)\}", tex))

    body = re.sub(r"\\num\{([^{}]*)\}", r" \1 ", body)
    body = re.sub(r"\\SI\{([^{}]*)\}\{([^{}]*)\}", r" \1 \2 ", body)
    body = re.sub(r"\\([A-Za-z]+)\b",
                  lambda mm: " " + macros[mm.group(1)] + " "
                  if mm.group(1) in macros else " ", body)
    body = re.sub(r"\\[^A-Za-z\s]", " ", body)      # \%, \&, \,
    body = re.sub(r"[{}~]", " ", body)
    body = body.replace("--", "-")
    return len([w for w in body.split() if re.search(r"[A-Za-z0-9]", w)])


def grab(tex: str, name: str) -> str | None:
    """Return the braced argument of \\name{...}, brace-matched."""
    m = re.search(r"\\" + name + r"\{", tex)
    if not m:
        return None
    i, depth = m.end(), 1
    while i < len(tex) and depth:
        if tex[i] == "\\":
            i += 2
            continue
        if tex[i] == "{":
            depth += 1
        elif tex[i] == "}":
            depth -= 1
        i += 1
    return tex[m.end():i - 1]


def drop(tex: str, name: str) -> str:
    """Delete every \\name{...} entirely, brace-matched."""
    out, i = [], 0
    needle = "\\" + name + "{"
    while True:
        j = tex.find(needle, i)
        if j < 0:
            out.append(tex[i:])
            return "".join(out)
        out.append(tex[i:j])
        k, depth, n = j + len(needle), 1, len(tex)
        while k < n and depth:
            if tex[k] == "\\":
                k += 2
                continue
            if tex[k] == "{":
                depth += 1
            elif tex[k] == "}":
                depth -= 1
            k += 1
        i = k


def first_authors(bib_path: pathlib.Path) -> dict[str, str]:
    """Map citation key -> first-author surname, parsed from references.bib."""
    bib = bib_path.read_text()
    out = {}
    for m in re.finditer(r"@\w+\{([^,]+),", bib):
        key = m.group(1).strip()
        block = bib[m.end():m.end() + 800]
        au = re.search(r"AUTHOR\s*=\s*\{(.*?)\}", block, re.S)
        if not au:
            continue
        first = au.group(1).split(" and ")[0].strip()
        surname = first.split(",")[0].strip() if "," in first else first.split()[-1]
        out[key] = surname
    return out


def convert_citations(tex: str, bib: dict[str, str]) -> tuple[str, int, int, int]:
    """Convert numeric \\cite to Harvard B (Style V).

    Three cases, decided by whether the words ALREADY in the prose before the
    citation are the first author of the cited work:

      * prose name IS the first author  -> \\citet{key}; the prose name is removed so
        natbib supplies it, giving "Xia et al. (2026)" and not "Xia et al. (Xia et al. 2026)".
      * prose name is something else (a second author, a publisher, a university)
        -> keep the prose, use \\citeyearpar{key}, giving "Kiefer and Vogelsang (2005)"
        and "Newcastle University (2020)".
      * no name in the prose -> \\citep{key}, giving "(Paez 2004)".

    The earlier heuristic (name ~= any capitalised word) turned "Newcastle University
    \\cite{uo_archive}" into "Newcastle James et al. (2020)" and doubled
    "Kiefer and Vogelsang". Testing the captured word against the bib's first author
    is what prevents that.
    """
    named = others = bare = 0

    def two_author(m):
        nonlocal others
        if m.group(2) not in bib:
            return m.group(0)
        others += 1
        return "%s~\\citeyearpar{%s}" % (m.group(1), m.group(2))

    tex = re.sub(
        r"([A-Z][A-Za-z'\-]+(?:,\s*[A-Z][A-Za-z'\-]+)*\s+and\s+[A-Z][A-Za-z'\-]+)"
        r"\s*~?\s*\\cite\{([^}]*)\}",
        two_author, tex)

    def one_author(m):
        nonlocal named, others
        key = m.group(2)
        surname = re.sub(r"\s+et\s+al\.?$", "", m.group(1)).strip()
        if surname == bib.get(key):
            named += 1
            return "\\citet{%s}" % key
        others += 1
        return "%s~\\citeyearpar{%s}" % (m.group(1), key)

    tex = re.sub(r"([A-Z][A-Za-z'\-]+(?:\s+et\s+al\.)?)\s*~?\s*\\cite\{([^}]*)\}",
                 one_author, tex)

    def bare_sub(m):
        nonlocal bare
        bare += 1
        return "\\citep{%s}" % m.group(1)

    tex = re.sub(r"\\cite\{([^}]*)\}", bare_sub, tex)
    return tex, named, others, bare


def convert_supplement(src: pathlib.Path, out: pathlib.Path, venue: str) -> str:
    """Convert main_si.tex to the peer-reviewed venue's class.

    The supplement carries the robustness tables and has no figures and no citations.
    `venue` is "peerj"; the branch for the withdrawn Taylor & Francis build was removed
    with that build.
    """
    si = (src / "main_si.tex").read_text()

    title = (grab(si, "Title") or "").strip()
    for n in ["Title", "Author", "AuthorNames", "corres", "address",
              "firstpage", "pubvolume", "issuenum", "articlenumber", "pubyear",
              "copyrightyear", "datereceived", "daterevised", "dateaccepted",
              "datepublished", "reftitle", "keyword", "abstract", "Abstract"]:
        si = drop(si, n)
    si = re.sub(r"\\makeatletter\n\\setcounter\{page\}\{\\@firstpage\}\n\\makeatother\n?", "", si)

    if venue != "peerj":
        raise SystemExit("only the PeerJ supplement is built; got venue=%r" % venue)

    # PeerJ's convention is "Supplemental Information S1"; the source title carries
    # the original wording.
    title = title.replace("Supplementary Material", "Supplemental Information S1")
    head = (
        "\\documentclass[fleqn,10pt]{wlpeerj}\n"
        "\\usepackage{siunitx}\n"
        # textcomp supplies the TEXT-font degree sign (\\textdegree), U+00B0 in Latin-1,
        # which survives PeerJ's font-map rewrite; the math-font $^\\circ$ (U+25E6) does
        # not. See convert_to_peerj.py for the full evidence.
        "\\usepackage{textcomp}\n"
        "\\usepackage{float}\n"          # the supplement uses [H] floats
        "\\usepackage{adjustbox}\n"      # wide tables scaled to the column
        # SET EVERY MINUS FROM THE OPERATORS FONT'S ASCII HYPHEN-MINUS. The supplement
        # prints 99 minus signs, and PeerJ's production pipeline rewrites the ToUnicode
        # map of the CM math-symbol font the default minus comes from, so those signs
        # leave the PDF as digits in the text layer ("-99" becomes "299"). ASCII survives
        # the rewrite because every encoding maps it identically. This is the same fix and
        # the same evidence as convert_to_peerj.py; the supplement needs its own copy
        # because it has its own preamble and is published as its own file.
        "\\DeclareMathSymbol{-}{\\mathbin}{operators}{\"2D}\n"
        "\\usepackage[hidelinks]{hyperref}\n"
        "\\usepackage{url}\n"
        "\\usepackage{xurl}\n"
        # THE SUPPLEMENT CITES, so it needs natbib and its own reference list. It names
        # Ripley's border correction, Donnelly's correction and spatstat -- the independent
        # cross-check in S16 rests on spatstat -- and it is published as its own file, so a
        # reader who downloads only the supplement must not be sent to the main text for
        # them. wlpeerj.cls already loads natbib and sets \\bibliographystyle{apalike}, which
        # is what gives PeerJ's "(Author, 2024)" form; no \\bibpunct is added here, because
        # in this class that is what REMOVES the comma.
        "\\renewcommand{\\thesection}{S\\arabic{section}}\n"
        "\\renewcommand{\\thetable}{S\\arabic{table}}\n"
        "\\renewcommand{\\theequation}{S\\arabic{equation}}\n\n"
        "\\title{" + title + "}\n"
        "\\author[1]{Wael Alnahari}\n\\author[2]{Ammar Arbaaeen}\n"
        "\\author[2]{Ammar Alsaig}\n\\author[1]{Tawfiq Hasanin}\n"
        "\\author[3]{Wasem Alnahri}\n"
        "\\affil[1]{Department of Information Systems, King Abdulaziz University, "
        "Jeddah 21589, Saudi Arabia}\n"
        "\\affil[2]{Department of Computer Science, Umm Al-Qura University, Mecca 24381, "
        "Saudi Arabia}\n"
        "\\affil[3]{Independent Researcher, Mecca 24331, Saudi Arabia}\n"
        "\\corrauthor[1]{Wael Alnahari}{walnahari0004@stu.kau.edu.sa}\n\n"
        # wlpeerj's title page prints \theabstract; without an abstract the class
        # raises Undefined control sequence. A supplement needs no abstract of its
        # own, so this states what the document is.
        "\\begin{abstract}\n"
        "Supplemental Information S1 for the manuscript. This document carries the "
        "robustness forks, sensitivity sweeps and estimator controls that the main "
        "text summarises but does not tabulate. Sections and tables are numbered with "
        "an S prefix so the main-text pointers resolve against this document.\n"
        "\\end{abstract}\n\n"
        "\\begin{document}\n\\flushbottom\\maketitle\\thispagestyle{empty}\n\n")

    idx = si.rindex("\\begin{document}") + len("\\begin{document}")
    body = si[idx:]
    body = re.sub(r"^\s*\\maketitle\s*", "", body)
    body = re.sub(r"\\end\{document\}\s*$", "", body)
    body = re.sub(r"^[ \t]*\\renewcommand\{\\the(?:section|table|equation)\}.*$",
                  "", body, flags=re.M)

    # Wide tables. A print page is wider than the review column, so a few of the
    # supplement's 6-7 column tabulars overflow. Wrap ONLY the tabular, never the
    # caption or the float, in an adjustbox that shrinks it when needed.
    def fit_tabular(m):
        tab = m.group(0)
        if tab.count("&") < 3:
            return tab
        return ("\\begin{adjustbox}{max width=\\linewidth}\n" + tab + "\n\\end{adjustbox}")

    body = re.sub(r"\\begin\{tabular\}\{[^}]*\}(?:(?!\\end\{tabular\}).)*\\end\{tabular\}",
                  fit_tabular, body, flags=re.S)

    # The supplement is published as its own file, so it carries its own declaration.
    si_ai = (
        "\n\\subsection*{Generative AI Use Disclosure Statement}\n"
        "\\noindent "
        "\\textbf{Tool and version.} GitHub Copilot 0.69.0, used to support LaTeX "
        "preparation and language editing of this supplement. "
        "It did not generate or alter any tabulated value; every table is produced by the "
        "analysis scripts in the deposit. "
        "\\textbf{Originality and accuracy.} The authors confirm the originality and accuracy "
        "of the content. "
        "\\textbf{Terms of use.} The authors have checked the tool's terms of use and confirm "
        "its use is suitable for publication. "
        "\\textbf{Responsibility.} The authors take full responsibility for the integrity of "
        "the whole content, including the accuracy of all references.\n")

    return head + body + si_ai + "\n\\end{document}\n"
