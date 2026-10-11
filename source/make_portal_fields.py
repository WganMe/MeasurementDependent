#!/usr/bin/env python3
"""Write the three text fields the PeerJ portal asks for, ready to paste.

WHY THIS EXISTS. The portal's Title/Abstract tab is not the manuscript: it is a set of
plain-text fields with their own limits, and its checklist warns about three things that a
PDF cannot warn you about --

    "Title and abstract entered exactly as you want them to appear in the final publication."
    "No linebreaks or strange characters in the abstract."
    "Special characters entered correctly (non-latin / latex)."

A copy-paste from the PDF would arrive with the line-number gutter, wrapped lines and the
typographic characters below, any of which can paste badly into a text box. So the values are
EXTRACTED from the built PDF and written into `portal-fields.md` as paste-ready text, the same
way every other value in this submission is read rather than retyped.

THE CHARACTERS THAT MATTER. The built abstract contains:

    U+2013  EN DASH        "2013-2026", "Clark-Evans"   standard typography, pastes fine
    U+2019  RIGHT SINGLE Q "year's"                     standard typography, pastes fine
    U+2212  MINUS SIGN     "-99 m per year"             NOT a hyphen-minus

U+2212 is the one to strip. It is a mathematical operator, not the keyboard character, and a
plain text field that does not expect maths can reject it, substitute it, or render it as a
missing glyph. It is replaced with the ASCII hyphen-minus, which reads identically here.

The en dash and the curly apostrophe are kept: they are ordinary published typography, PeerJ
itself uses them, and their ASCII stand-ins would be a change to the text rather than a repair
to it. Only the minus is normalised, and the script reports every character it changed.

USAGE
    python3 make_portal_fields.py        # writes ../portal-fields.md
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent                      # the submission root, one level up

# THE LIMITS COME FROM THE FORM'S OWN maxlength ATTRIBUTES, not from a screenshot's counter.
# Read off the portal markup for manuscript 150843:
#   title        maxlength="250"
#   shortTitle   maxlength="40"
#   abstract     maxlength="3000"   and a stated MINIMUM of 500 characters
#
# An earlier version of this file used 50 and 2000, misread from the counters on screen, and
# the short-title recommendation it produced was 45 characters -- five over the real limit.
# The `maxlength` attribute is what the browser enforces, so it is what is checked here.
TITLE_LIMIT = 250
SHORT_LIMIT = 40
ABSTRACT_LIMIT = 3000                  # CHARACTERS, not words
ABSTRACT_MIN = 500                     # the form refuses less than this

# The published title and the portal title MUST match: the portal says plainly, "This text
# will be used in your published article (not the text from your manuscript document)".
# PeerJ asks for SENTENCE CASING and its own form warns against many capitals, and the
# published example in the same journal uses it:
#   "A spatially interpretable machine learning framework for urban waterlogging risk
#    mapping in Beijing"
# The manuscript's title is Title Case. A naive sentence-caser would also lowercase "Urban
# Observatory", which is a proper noun (the Newcastle Urban Observatory platform), so the
# compliant form is written out by hand rather than generated:
TITLE_SENTENCE_CASE = (
    "Measurement-dependent clustering in the growing "
    "Urban Observatory sensor network")

# The form supports inline markup: [b] [i] [sup] [sub]. Neither the title nor the abstract
# needs any of it, so no markup is emitted. The abstract also accepts LaTeX equations
# (\(...\), $$...$$, \[...\]); this abstract contains no equation.

# Characters whose ASCII form is a faithful stand-in. Anything not listed is left alone and
# reported, so a new character cannot slip through unnoticed.
NORMALISE = {
    "\u2212": "-",      # MINUS SIGN -> hyphen-minus
    "\u00a0": " ",      # NO-BREAK SPACE -> ordinary space
    "\u2010": "-",      # HYPHEN
    "\u2011": "-",      # NON-BREAKING HYPHEN
    "\u2012": "-",      # FIGURE DASH
}

# The portal wants a short title (<= 40 characters) and the manuscript has none: it is a
# portal-only field. The guidance is "make your short title as descriptive as possible", and
# the examples given are noun phrases ("Canada buffaloberry demographic effects"), so these are
# noun phrases. This is a RECOMMENDATION, not a value read from the paper -- the author can
# replace it. Neither uses an acronym, which the title guidelines ask to avoid.
SHORT_TITLE = "Measurement-dependent sensor clustering"          # 39
SHORT_TITLE_ALTERNATIVES = [
    "Measurement-dependent urban clustering",                    # 38
    "Measurement-dependent clustering",                          # 32
    "Urban observatory clustering is measurement-dependent",     # 53 -- too long, kept out
]
SHORT_TITLE_ALTERNATIVES = [a for a in SHORT_TITLE_ALTERNATIVES if len(a) <= SHORT_LIMIT]


# THE AUTHOR INFORMATION TAB. Read out of `peerj-main.tex` rather than typed here, so a name
# or affiliation that changes in the manuscript changes here too. The ORCIDs are the one
# thing the manuscript does not carry, so they are held with the manuscript's own comment
# naming them as the authors' own, and each is CHECKED BY CHECKSUM below: an ORCID's last
# character is a mod-11-2 check digit, so a mistyped one fails arithmetic rather than needing
# to be noticed by eye. The portal publishes these, so a wrong one is a wrong identifier
# attached to a real person.
ORCIDS = {
    "Wael Alnahari": "0000-0001-5247-3713",
    "Ammar Arbaaeen": "0000-0003-2165-3185",
    "Ammar Alsaig": "0000-0002-6756-9766",
    "Tawfiq Hasanin": "0000-0003-1072-278X",
    "Wasem Alnahri": "0009-0004-6963-5773",
}


def orcid_ok(orcid: str) -> bool:
    """The ORCID mod-11-2 check digit. False for anything mistyped or invented."""
    digits = orcid.replace("-", "")
    if not re.fullmatch(r"\d{15}[\dX]", digits) or len(orcid) != 19:
        return False
    total = 0
    for d in digits[:15]:
        total = (total + int(d)) * 2
    result = (12 - total % 11) % 11
    return ("X" if result == 10 else str(result)) == digits[15]


def keywords_from_tex() -> list[str]:
    """The manuscript's \\keyword{} as a list, in its own order.

    Read rather than retyped so a keyword added to the paper appears here, and one removed
    from the paper stops being offered at the portal. The peerJ class disables the keywords
    block, so this list exists ONLY in the source and in the portal -- there is no printed
    list in the manuscript for a reader to compare against.
    """
    tex = (OUT / "source" / "main.tex").read_text(encoding="utf-8")
    m = re.search(r"\\keyword\{([^{}]*)\}", tex, re.S)
    if not m:
        raise SystemExit("REFUSING: no \\keyword{} in source/main.tex")
    return [k.strip() for k in re.sub(r"\s+", " ", m.group(1)).split(";") if k.strip()]


def authors_from_tex(pdf: pathlib.Path) -> list[tuple[str, str]]:
    """(author, affiliation) pairs, in the order the manuscript lists them."""
    tex = (OUT / "peerj-main.tex").read_text(encoding="utf-8")
    affils = dict(re.findall(r"\\affil\[(\d+)\]\{([^}]*)\}", tex))
    out = []
    for n, name in re.findall(r"\\author\[(\d+)\]\{([^}]*)\}", tex):
        out.append((name.strip(), affils.get(n, "").strip()))
    if not out:
        raise SystemExit("REFUSING: no \\author[]{}{} entries in peerj-main.tex")
    return out


def competing_from_tex() -> str:
    """The Competing Interests statement, as the manuscript words it.

    PeerJ's form requires complete sentences and says that if there are no competing interests
    then that fact must be stated explicitly. This manuscript has a NON-FINANCIAL interest --
    the authors prepared the benchmark artifact whose provenance the paper audits -- so
    answering "no competing interests" here would contradict the published statement.

    Note the form's own example wording: PeerJ permits naming an academic-editor role. None is
    declared here, and inventing one would be false.
    """
    tex = (OUT / "source" / "main.tex").read_text(encoding="utf-8")
    m = re.search(r"\\conflictsofinterest\{(.*?)\}\n\n", tex, re.S)
    if not m:
        raise SystemExit("REFUSING: no \\conflictsofinterest{} in source/main.tex")
    body = re.sub(r"\s+", " ", m.group(1)).strip()
    # Resolve the source's LaTeX citation to the form the paper PRINTS. Left as \cite, the
    # paste-ready text would carry LaTeX into a plain-text field, which is exactly what the
    # portal's "special characters entered correctly" warning is about.
    #
    # The rendered form is "Newcastle University (2020)", NOT "(Newcastle University, 2020)".
    # The sentence already says "published by Newcastle University", so the parenthetical form
    # would repeat the name -- checked against the built PDF rather than assumed.
    body = re.sub(r"\\cite\{uo_archive\}", "(2020)", body)
    if "\\" in body:
        raise SystemExit("REFUSING: LaTeX remains in the competing-interest text: %r"
                         % re.search(r".{0,30}\\.{0,30}", body).group(0))
    return body


def funding_from_tex() -> tuple[str, str]:
    """(funding statement, grant number) as the manuscript words them.

    The form forbids financial information in the Acknowledgments and forbids the words
    'generous', 'thankful', 'thanks' and 'acknowledge' in this statement, so the wording comes
    from the manuscript's own \\funding block rather than being composed here.
    """
    tex = (OUT / "source" / "main.tex").read_text(encoding="utf-8")
    m = re.search(r"\\funding\{(.*?)\}\n\n", tex, re.S)
    if not m:
        raise SystemExit("REFUSING: no \\funding{} in source/main.tex")
    funding = re.sub(r"\s+", " ", m.group(1)).strip()
    g = re.search(r"\\newcommand\{\\uquGrant\}\{([^}]*)\}", tex)
    if not g:
        raise SystemExit("REFUSING: no \\uquGrant definition in source/main.tex")
    grant = g.group(1).strip()
    if "\\uquGrant" in funding:
        funding = funding.replace("\\uquGrant{}", grant)
    return funding, grant


def zenodo_text() -> str:
    """The repository-access text for question 92, read from the published record.

    The DOI is taken from `ZENODO_RECORD.json` rather than typed here, because typing it went
    wrong once already: the text named the v1.0.6 accession after v1.0.7 had been published.
    The concept DOI is the one the manuscript cites, and it is the one the form should be given
    as the link -- it always resolves to the current version.
    """
    rec = json.loads((OUT / "source" / "ZENODO_RECORD.json").read_text(encoding="utf-8"))
    doi, concept = rec.get("doi"), rec.get("conceptdoi")
    if not doi or not concept:
        raise SystemExit("REFUSING: ZENODO_RECORD.json has no doi/conceptdoi")
    return (
        "1. Repository/database name: Zenodo\n"
        "2. Accession/id number: %s (version %s); concept DOI %s\n"
        "3. Link: https://doi.org/%s\n\n"
        "The concept DOI is the one cited in the manuscript and always resolves to the current "
        "version. The deposit carries the derived census, the fitted models, the snapshot audit "
        "and every analysis script behind the numbers in the paper, under CC BY 4.0."
        % (doi, rec.get("version"), concept, concept))


def combined_data_text(zenodo: str) -> str:
    """The single textarea the form's "Both" selection shows, as one block.

    The form joins its two prompts with the word "and" and presents ONE textarea, so the
    supplementary-file description and the repository description have to arrive together.
    Building it from the same two pieces the other branches use keeps the three texts in
    agreement -- the earlier version printed them separately, which would have left half the
    field empty.
    """
    return (
        "The analysis code and the results behind every number and table are provided as "
        "supplementary files, and the same material is openly archived in a repository.\n"
        "\n"
        "Supplementary files: source_code_and_results.zip carries the analysis scripts, the "
        "JSON result file behind every number and table, the figure generators, and the "
        "committed inputs they read (the per-year instrument census and the one-week instrument "
        "catalogue); the scripts run from the archive as it stands. source_main.zip carries the "
        "manuscript source, its bibliography, the four cited figure PDFs and the PeerJ class "
        "file; source_si.zip carries the supplement source. "
        "2_supplemental_information_S1.pdf tabulates the robustness forks, sensitivity sweeps "
        "and estimator controls that the main text summarises.\n"
        "\n"
        + zenodo)


def archive_facts() -> dict:
    """Counts and sizes of the built upload bundle, read from the archives themselves.

    The Title and Legend fields describe files a reader will open, so the numbers in them have
    to be the real ones. Reading them here means a description cannot drift from the archive it
    describes -- and PeerJ validates this field ("Check file & file type"), so a wrong count is
    a visible error rather than a cosmetic one.

    The form marks "Copied text from the article" as BAD for the Legend, so the text below
    describes the FILES -- what is in the archive and how to use it -- rather than restating the
    manuscript.
    """
    import zipfile
    out = os.path.join(OUT, "dist")
    # ONLY DIRECTORIES. `sorted(...)[-1]` picked `PeerJ_submission_<date>.zip`, because
    # alphabetically the `.zip` sorts after the bare date, so every lookup inside it failed and
    # the counts silently came out empty. The bundle is also written as a zip of the same name,
    # which is what made this a silent failure rather than a crash.
    dates = sorted(d for d in os.listdir(out)
                   if d.startswith("PeerJ_submission_")
                   and os.path.isdir(os.path.join(out, d))) if os.path.isdir(out) else []
    # THE BUNDLE MAY NOT EXIST YET, and that is not an error. build.sh runs this generator
    # BEFORE make_peerj_bundle.py, because the portal values describe the documents the bundle
    # is built from. So the counts are best-effort: when the archives are present they are read
    # and printed, and when they are not, the descriptions are written without counts rather
    # than refusing. Refusing here broke `./build.sh` outright, which is how I found it.
    if not dates:
        return {}
    bundle = os.path.join(out, dates[-1])

    def facts(name):
        path = os.path.join(bundle, name)
        if not os.path.exists(path):
            return None
        with zipfile.ZipFile(path) as z:
            files = [i.filename for i in z.infolist() if not i.is_dir()]
        return {"n": len(files), "kb": os.path.getsize(path) / 1024, "files": files}

    return {n: f for n in ("source_main.zip", "source_si.zip",
                           "source_code_and_results.zip")
            if (f := facts(n)) is not None}


def figure_legends() -> list[tuple[str, str, str]]:
    """(filename, title, legend) for each cited figure, in citation order.

    The portal marks "Copied text from the article" as BAD for a Legend, so each legend
    DESCRIBES what the figure shows rather than reproducing the caption. The titles are
    therefore not the captions either; they name the subject and the quantity. The order is
    the citation order, which is also the order the files are numbered.
    """
    return [
        ("Figure 1.pdf",
         "The merge tolerance: how the clustering index varies with the merge radius",
         "Two panels. (a) The fall in the clustering index on the fixed reference hull, from "
         "2013 to 2026, plotted against the radius within which nearby registrations are merged "
         "into one location; a dashed line marks the 25 m radius used in the analysis and a "
         "second series gives the associated p-value on the right-hand axis. (b) The "
         "nearest-neighbour distance distributions for a recent and the final year, on a "
         "logarithmic axis, which is what shows whether a natural threshold exists between "
         "co-located and distinct instruments."),
        ("Figure 2.pdf",
         "Instrument population of the Urban Observatory, 2013 to 2026, with arrivals and "
         "departures",
         "A line gives the number of instruments reporting in each year. Two bar series "
         "underneath count the instruments appearing for the first time in that year and those "
         "seen for the last time, drawn above and below the axis. Read together they show that "
         "the population grows by turnover rather than as a steady ramp."),
        ("Figure 3.pdf",
         "Clustering index by year on the fixed reference hull, with rarefaction and the "
         "expected envelope",
         "The annual clustering index for both units of analysis, with the same series rarefied "
         "to a common sample size shown faintly so that the changing instrument count cannot "
         "drive the trend, and a horizontal line at the value expected under complete spatial "
         "randomness. Fitted trends are drawn over the series, which is what shows the trend "
         "disappearing once the sample size is held fixed."),
        ("Figure 4.pdf",
         "The study area: the fixed reference hull and each year's bounding box",
         "Two panels. (a) The fixed reference hull that all years are measured against, with "
         "the first and last years' instrument locations plotted on it. (b) Each year's own "
         "bounding box shown as a share of that hull, which is what makes the reference frame "
         "used for a given year visible."),
    ]


def pdf_text(pdf: pathlib.Path) -> str:
    p = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit("REFUSING: pdftotext failed on %s" % pdf)
    return p.stdout


def abstract_from_pdf(pdf: pathlib.Path) -> str:
    """The abstract as a reader sees it, flattened to ONE line.

    The line-number gutter ("  14   ") is stripped and every run of whitespace collapsed,
    because the portal warns specifically about linebreaks in the abstract field.
    """
    txt = pdf_text(pdf)
    s = txt.index("ABSTRACT") + len("ABSTRACT")
    e = txt.index("INTRODUCTION")
    body = re.sub(r"(?m)^\s*\d{1,3}\s{1,6}", "", txt[s:e])
    return re.sub(r"\s+", " ", body).strip()


def title_from_source(pdf: pathlib.Path) -> str:
    """The title from `peerj-main.tex`, then CHECKED against the built PDF.

    Parsing it out of the PDF header is unreliable: the title wraps over two lines and every
    line begins with the line-number gutter (" 1   Measurement-Dependent Clustering in the"),
    so a naive read picked up an empty string. The `.tex` has it in one piece.

    The source is not trusted on its own, though -- the point of this script is that a portal
    value must match what the PDF actually says. So the extracted title is asserted present in
    the PDF's first-page text before it is used.
    """
    tex = (OUT / "peerj-main.tex").read_text(encoding="utf-8")
    m = re.search(r"\\title\{([^{}]*)\}", tex)
    if not m:
        raise SystemExit("REFUSING: no \\title{} in peerj-main.tex")
    title = re.sub(r"\s+", " ", m.group(1)).strip()

    # Compare against the PDF with the line-number gutter removed: every line of the review
    # PDF starts with a number, so "the\n 2    Growing" becomes "the 2 Growing" and a plain
    # substring test fails on a title that is in fact printed correctly.
    page = re.sub(r"(?m)^\s*\d{1,3}\s{1,6}", "", pdf_text(pdf))
    page = re.sub(r"\s+", " ", page)
    if title not in page:
        raise SystemExit(
            "REFUSING: the title in peerj-main.tex is not the title printed in the PDF.\n"
            "  .tex : %s" % title)
    return title


def normalise(text: str) -> tuple[str, Counter]:
    """Replace the characters whose ASCII stand-in is exact; count every replacement."""
    changed = Counter()
    out = []
    for ch in text:
        if ch in NORMALISE:
            changed[ch] += 1
            out.append(NORMALISE[ch])
        else:
            out.append(ch)
    return "".join(out), changed


# Faithful ASCII forms for the typographic characters a paste can mangle. These CHANGE the
# text, which is why they are not applied to the primary copy; they exist so there is a
# fallback that cannot paste badly.
ASCII_FOLD = {
    "\u2013": "-",      # en dash
    "\u2014": "--",     # em dash
    "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"',
    "\u2026": "...",
    "\u00a0": " ",
    "\u2212": "-",
}


def ascii_fold(text: str) -> tuple[str, Counter]:
    """Map every non-ASCII character to a faithful ASCII form; report what changed."""
    changed = Counter()
    out = []
    for ch in text:
        if ord(ch) < 128:
            out.append(ch)
        elif ch in ASCII_FOLD:
            changed[ch] += 1
            out.append(ASCII_FOLD[ch])
        else:
            changed[ch] += 1
            out.append("?")            # nothing sensible to map to: make it visible
    return "".join(out), changed


def main() -> int:
    pdf = OUT / "peerj-main.pdf"
    if not pdf.exists():
        print("REFUSING: %s not found. Run convert_to_peerj.py and pdflatex first." % pdf)
        return 1

    raw_title = title_from_source(pdf)
    raw_abstract = abstract_from_pdf(pdf)
    title, t_changed = normalise(raw_title)
    abstract, a_changed = normalise(raw_abstract)

    # A second, fully ASCII copy of the abstract, for the "no strange characters" warning.
    # The portal's own help says to use an online text-cleaning tool when a paste brings
    # strange characters in. Rather than trusting a cleaner to leave the text alone, this is
    # the text with every non-ASCII character mapped to a faithful ASCII form, so there is a
    # version that cannot paste badly if the typographic one does. It is generated for
    # comparison, and the differences are counted so the two can be checked by eye.
    ascii_abstract, ascii_changed = ascii_fold(abstract)

    # --- the portal's own limits, enforced here rather than discovered at the portal
    problems = []
    if len(title) > TITLE_LIMIT:
        problems.append("title is %d characters, limit %d" % (len(title), TITLE_LIMIT))
    if len(SHORT_TITLE) > SHORT_LIMIT:
        problems.append("short title is %d characters, limit %d"
                        % (len(SHORT_TITLE), SHORT_LIMIT))
    if len(TITLE_SENTENCE_CASE) > TITLE_LIMIT:
        problems.append("sentence-case title is %d characters, limit %d"
                        % (len(TITLE_SENTENCE_CASE), TITLE_LIMIT))
    if len(abstract) > ABSTRACT_LIMIT:
        problems.append("abstract is %d characters, limit %d"
                        % (len(abstract), ABSTRACT_LIMIT))
    if len(abstract) < ABSTRACT_MIN:
        problems.append("abstract is %d characters, MINIMUM is %d"
                        % (len(abstract), ABSTRACT_MIN))
    if "\n" in abstract:
        problems.append("abstract contains a linebreak")

    authors = authors_from_tex(pdf)
    kw = keywords_from_tex()
    COMPETING = competing_from_tex()
    FUNDING, GRANT = funding_from_tex()
    ZENODO_TEXT = zenodo_text()
    COMBINED_TEXT = combined_data_text(ZENODO_TEXT)
    ARCHIVE_FACTS = archive_facts()
    for name, _affil in authors:
        o = ORCIDS.get(name)
        if o is None:
            problems.append("no ORCID recorded for %s" % name)
        elif not orcid_ok(o):
            problems.append("ORCID for %s (%s) fails its checksum" % (name, o))
    # The keywords checklist item is NEGATIVE: they must NOT be listed in the manuscript. That
    # is checkable. A printed list puts two keywords adjacent, so the test looks for adjacent
    # PAIRS; a single keyword appearing as ordinary prose ("An urban sensor network is usually
    # presented as a fixed capability") is not a list and must not trip this.
    pdf_words = re.sub(r"\s+", " ", pdf_text(pdf)).lower()
    adjacent = sum(1 for a, b in zip(kw, kw[1:])
                   if (a.lower() + "; " + b.lower())[:40] in pdf_words)
    if adjacent:
        problems.append("the manuscript appears to PRINT the keyword list (%d adjacent pair(s) "
                        "found); PeerJ asks that keywords not be listed in the manuscript"
                        % adjacent)
    if problems:
        raise SystemExit("REFUSING: " + "; ".join(problems))

    def changed_note(counter):
        if not counter:
            return "no character substitutions were needed"
        return ", ".join("U+%04X %s replaced x%d with %r"
                         % (ord(c), c, n, NORMALISE[c]) for c, n in counter.items())

    doc = []
    doc.append("# PeerJ portal text fields — paste these exactly\n")
    doc.append("Generated by `source/make_portal_fields.py` from the built `peerj-main.pdf`, "
               "not retyped.\n")
    doc.append("The portal's checklist asks that these be entered *\"exactly as you want them "
               "to appear in the final publication\"*, with no linebreaks and correct special "
               "characters. The fenced blocks below are the exact strings to paste.\n")

    doc.append("## Title — %d of %d characters\n" % (len(title), TITLE_LIMIT))
    doc.append("The portal states plainly: *\"This text will be used in your published article "
               "(not the text from your manuscript document).\"* So the title below must be the "
               "published title, and it must match what the PDF prints.\n")
    doc.append("**Paste this one.** PeerJ asks for sentence casing, and its form warns when a "
               "title carries many capitals. This is the manuscript's title in sentence case, "
               "with `Urban Observatory` kept capitalised because it is the name of the "
               "Newcastle platform, not a common noun — an automatic sentence-caser would "
               "wrongly lowercase it.\n")
    doc.append("```text")
    doc.append(TITLE_SENTENCE_CASE)
    doc.append("```\n")
    doc.append("The manuscript PDF prints the Title Case form, and the two must not drift:\n")
    doc.append("```text")
    doc.append(title)
    doc.append("```\n")
    doc.append("Either is within the %d-character limit; the sentence-case one is what PeerJ "
               "asks for. If you prefer the Title Case form in the published article, paste "
               "that instead.\n" % TITLE_LIMIT)

    doc.append("## Short Title — %d of %d characters\n"
               % (len(SHORT_TITLE), SHORT_LIMIT))
    doc.append("**This one is a recommendation, not a value read from the paper:** the "
               "manuscript carries no short title, because the portal is the only place that "
               "asks for one. The limit is **%d** characters (the form's `maxlength`), and the "
               "guidance is to make it as descriptive as possible. Replace it if you prefer "
               "another.\n" % SHORT_LIMIT)
    doc.append("```text")
    doc.append(SHORT_TITLE)
    doc.append("```\n")
    doc.append("Alternatives, all within the limit:\n")
    for alt in SHORT_TITLE_ALTERNATIVES:
        doc.append("- `%s` (%d)" % (alt, len(alt)))
    doc.append("")

    doc.append("## Abstract — %d of %d characters, %d words, one line\n"
               % (len(abstract), ABSTRACT_LIMIT, len(abstract.split())))
    doc.append("The limit is **characters, not words** — and it is a **range**: `maxlength` is "
               "%d and the form refuses fewer than **%d**. This abstract is %d, comfortably "
               "inside both. Every other place in this submission counts the abstract in words "
               "(199), which is a different number and does not substitute for this one. The "
               "field is a single paragraph, so the text carries no linebreaks.\n"
               % (ABSTRACT_LIMIT, ABSTRACT_MIN, len(abstract)))
    doc.append("**Paste this one.**\n")
    doc.append("```text")
    doc.append(abstract)
    doc.append("```\n")

    doc.append("### If the paste brings strange characters: a fully ASCII copy\n")
    doc.append("The portal's checklist warns about *\"linebreaks or strange characters\"* and "
               "suggests an online text-cleaning tool. This is the same abstract with every "
               "non-ASCII character mapped to a faithful ASCII form, so there is a version "
               "that cannot paste badly. It **changes the text** (%s), which is why it is the "
               "fallback rather than the default — prefer the copy above.\n"
               % ", ".join("%s x%d" % (c, n) for c, n in sorted(ascii_changed.items()))
               if ascii_changed else
               "The portal's checklist warns about *\"linebreaks or strange characters\"* and "
               "suggests an online text-cleaning tool. This abstract has no non-ASCII "
               "characters at all, so a plain paste cannot go wrong.\n")
    if ascii_changed:
        doc.append("```text")
        doc.append(ascii_abstract)
        doc.append("```\n")
        doc.append("The differences, so the two can be checked by eye:\n")
        for ch, n in sorted(ascii_changed.items(), key=lambda kv: -kv[1]):
            doc.append("- `%s` (U+%04X) → `%s`  ×%d" % (ch, ord(ch), ASCII_FOLD.get(ch, "?"), n))
        doc.append("")

    doc.append("## Author information — the portal's next tab\n")
    doc.append("Read out of the manuscript (`peerj-main.tex`), so a name or affiliation that "
               "changes in the paper changes here. The ORCIDs are the one value the "
               "manuscript does not carry; each was checked by its own mod-11-2 check digit, "
               "which is why a mistyped one cannot pass unnoticed.\n")
    doc.append("| # | Author | Affiliation | ORCID |")
    doc.append("| --- | --- | --- | --- |")
    for i, (name, affil) in enumerate(authors, 1):
        doc.append("| %d | %s | %s | `%s` |" % (i, name, affil, ORCIDS[name]))
    doc.append("")
    doc.append("Corresponding author and e-mail, as the manuscript prints them:\n")
    doc.append("```text")
    doc.append("Wael Alnahari — walnahari0004@stu.kau.edu.sa")
    doc.append("```\n")
    doc.append("The manuscript does **not** print ORCIDs in the title block, and the published "
               "PeerJ paper beside this one prints none either, so there is nothing to match "
               "in the PDF; the portal is where they are entered and where they will be "
               "published. Confirm each against the author's own ORCID record before saving: "
               "the checksums prove the identifiers are well-formed, not that they belong to "
               "the right people.\n")

    doc.append("## Subject areas — the portal's list, not ours\n")
    doc.append("PeerJ's subjects are a fixed taxonomy: the portal presents them and you tick "
               "the ones that apply. These are spelled exactly as PeerJ spells them, so they "
               "can be matched against the portal's own list (see `portal-values.md`, which "
               "carries the verified subject URLs):\n")
    doc.append("- **Spatial and Geographic Information Systems** — primary")
    doc.append("- Environmental Monitoring & Management")
    doc.append("- Data Mining and Machine Learning")
    doc.append("- Internet of Things")
    doc.append("- Network Science and Online Social Networks")
    doc.append("")
    doc.append("PeerJ names this subject **Systems**, not *Science*; the published example "
               "paper's own subject line reads *Spatial and Geographic Information Science*, so "
               "take whichever the portal's list actually offers.\n")

    # KEYWORDS: read from the manuscript, not retyped. The portal takes UP TO 10 and asks for
    # "the core concepts of your manuscript"; the manuscript's \keyword{} carries six. Its
    # checklist also states the keywords must NOT appear listed in the manuscript itself --
    # true here, because wlpeerj.cls disables the keywords block, so the portal is the only
    # place they are listed. Checked against the built PDF rather than assumed.
    doc.append("## Keywords — %d, the portal takes up to 10\n" % len(kw))
    doc.append("From `\\keyword{}` in the manuscript, one per line for the portal's Add box. "
               "PeerJ's class disables the keywords block, so the portal is the **only** place "
               "they are listed -- which is what the checklist's *\"keywords are not listed in "
               "your manuscript\"* item asks for.\n")
    for k in kw:
        doc.append("- `%s`" % k)
    doc.append("")
    doc.append("As one line, if the portal's field prefers that:\n")
    doc.append("```text")
    doc.append("; ".join(kw))
    doc.append("```\n")

    doc.append("## Generative AI declaration — the answer is YES\n")
    doc.append("The portal asks: *\"Did you use an Artificial Intelligence tool (e.g. generative "
               "AI, large language model (LLM), etc.) to write or edit text, generate images or "
               "figures, or generate data?\"* **Answer Yes.** The manuscript already declares it "
               "in full, so answering No would contradict the paper itself.\n")
    doc.append("Tick what was done, and only that:\n")
    doc.append("| The form's option | Answer | Why |")
    doc.append("| --- | --- | --- |")
    doc.append("| write or edit text | **Yes** | the disclosure names GitHub Copilot for "
               "\"drafting and editing LaTeX and typesetting support\" |")
    doc.append("| generate images or figures | **No** | every figure is produced by a "
               "matplotlib script from a committed results file; the four cited figures are "
               "pure vector PDFs with no raster content |")
    doc.append("| generate data | **No** | no tool computed, altered or selected any result; "
               "the disclosure says so explicitly |")
    doc.append("")
    doc.append("Description to paste, taken from the manuscript's own disclosure so the form "
               "and the paper cannot say different things:\n")
    doc.append("```text")
    doc.append("Drafting and editing LaTeX and typesetting support. The tool was not used to "
               "compute, alter or select any result; every number in the manuscript is read "
               "from a committed results file produced by the analysis scripts in the deposit. "
               "The authors have checked the tool's terms of use and take full responsibility "
               "for the integrity of the whole content, including the accuracy of all "
               "references.")
    doc.append("```\n")

    doc.append("## Competing Interest statement\n")
    doc.append("The form requires complete sentences and says: *\"If there are no competing "
               "interests then you must explicitly state this fact.\"* This manuscript has a "
               "**non-financial** interest to declare, and it is declared in the paper, so the "
               "form must not say \"no competing interests\" -- that would contradict the "
               "published statement. Paste:\n")
    doc.append("```text")
    doc.append(COMPETING)
    doc.append("```\n")

    doc.append("## Funding statement\n")
    doc.append("The form requires **every** external funding source named, with the agency and "
               "the grant number, and says *\"All funding must be declared completely here\"*. "
               "It also forbids financial information in the Acknowledgments and forbids "
               "*'generous'*, *'thankful'*, *'thanks'* and *'acknowledge'* in this statement. "
               "Paste:\n")
    doc.append("```text")
    doc.append(FUNDING)
    doc.append("```\n")
    doc.append("The grant number is read from the manuscript's `\\uquGrant` macro, so it cannot "
               "differ from what the paper and the cover page print:\n")
    doc.append("```text")
    doc.append(GRANT + " (Umm Al-Qura University, Deanship of Postgraduate Studies and "
               "Scientific Research) -- this is the `Grant Disclosures` field")
    doc.append("```\n")

    doc.append("## Declarations tab — the three Yes/No questions\n")
    doc.append("Each is **No**, checked against the sources rather than assumed:\n")
    doc.append("| Question | Answer | Checked |")
    doc.append("| --- | --- | --- |")
    doc.append("| Do you name, or make use of, any patents in your text? | **No** | zero "
               "occurrences of \"patent\" in `main.tex` and `main_si.tex` |")
    doc.append("| Do you report on any DNA/RNA/peptide etc. sequencing? | **No** | zero for "
               "DNA, sequencing, peptide and GenBank; the \"RNA\" and \"sequence\" matches are "
               "inside *alternative*, *internal* and \"temporal sequence\" and are not "
               "biological |")
    doc.append("| Did you perform any microarray experiments? | **No** | zero occurrences of "
               "\"microarray\" |")
    doc.append("")
    doc.append("Each is a **No**, so its conditional follow-up stays hidden. Answering Yes "
               "would open a required field with nothing to put in it.\n")

    doc.append("## Declarations tab — raw data and code (question 90)\n")
    doc.append("Select **\"Both upload to PeerJ & Submit repository link(s) to data\"**. The "
               "Data Availability statement says both, and both are true:\n")
    doc.append("- the census, models, snapshot audit and every analysis script are archived at "
               "the DOI, and")
    doc.append("- they are \"also provided as Supplemental Information\", which the bundle now "
               "does with `source_code_and_results.zip`.")
    doc.append("")
    doc.append("> **This was not true until 2026-10-11.** The manuscript claimed the code was "
               "provided as Supplemental Information, but the uploaded archives held only "
               "LaTeX sources -- no code at all. The portal states in bold that a submission "
               "cannot be reviewed without the code, so the claim and the upload disagreed. "
               "`source_code_and_results.zip` closes that gap; see the note below.")
    doc.append("")
    doc.append("Describe the uploaded files **and** the repository access (question 93):\n")
    doc.append("**This is the field the *Both* selection shows, and it is ONE textarea.** "
               "The form labels it with both prompts joined by *and* -- describe the "
               "supplementary files, AND describe the files you are providing repository access "
               "to, numbered 1-3. Paste this single block:\n")
    doc.append("```text")
    doc.append(COMBINED_TEXT)
    doc.append("```\n")
    doc.append("If the other branches are ever chosen instead, their separate texts are:\n")
    doc.append("- *Upload to PeerJ* only (question 91) — the first paragraph above.\n")
    doc.append("- *Submit repository link(s)* only (question 92) — the numbered three lines "
               "above, without the supplementary-file paragraph.\n")

    doc.append("## Declarations — Other tab\n")
    doc.append("Four optional fields on the *Other* tab.\n")
    doc.append("**Societies or professional associations.** Stated by the author, not read "
               "from the paper -- nothing in the repository records a membership, so this is "
               "recorded here as given:\n")
    doc.append("```text")
    doc.append("Senior Member, IEEE")
    doc.append("```\n")
    doc.append("*IEEE's grades are Student Member, Member, Senior Member, Fellow, Life Member, "
               "Life Senior and Life Fellow, so `Senior Member` is the grade itself and needs no "
               "qualifier. If more than one author holds a membership, name each one — the field "
               "is a list, and an unqualified entry would read as though it applied to every "
               "author.*\n")
    doc.append("**SI code (Special Issue or Collection).** Leave **blank**. That box takes a "
               "code issued by PeerJ. The only special-issue identifier anywhere in this "
               "project is `281361` — the MDPI *Symmetry* issue that was WITHDRAWN — so it must "
               "not be entered. This is a regular Research Article submission.\n")
    doc.append("**Was PeerJ recommended to you by someone?** Leave blank unless it was. If it "
               "was, the form wants the person's name and e-mail and will contact them, so this "
               "is an author's answer, not a derivable one.\n")
    doc.append("**Any other Information for the Academic Editor and Reviewers.** Left blank "
               "deliberately. It is optional, and its content is the author's judgement about "
               "what an editor should be told — not something to be composed on their behalf.\n")

    doc.append("## Every upload needs a Title and a Legend\n")
    doc.append("The portal asks for a one-sentence **Title** and a **Legend** on every "
               "uploaded file, in BOTH sections. Its help marks *\"Copied text from the "
               "article\"* as **BAD** for the Legend, so each Legend describes what the file "
               "IS -- its contents and how it is used -- rather than restating the paper. The "
               "figure legends describe what each figure shows; the captions in the manuscript "
               "are what they must NOT be copied from.\n")
    doc.append("**Set the File type of each upload as shown.** `source_main.zip` and "
               "`source_si.zip` are both LaTeX source; leaving the supplement's archive typed "
               "*data or code* is wrong, because it contains neither.\n")

    doc.append("### Section 1 — Manuscript (US Letter)\n")
    doc.append("```text")
    doc.append("1_manuscript.pdf   File type: Manuscript")
    doc.append("Title:  Measurement-dependent clustering in the growing Urban Observatory "
               "sensor network")
    doc.append("Legend: The complete manuscript, line-numbered for review. It reports a "
               "13-year census of the Newcastle Urban Observatory instrument population and "
               "asks how much of the apparent strengthening of nearest-neighbour clustering is "
               "a property of the deployment rather than of the measurement.")
    doc.append("```\n")

    doc.append("### Section 1 — Primary files: Hi-res figures and tables\n")
    doc.append("The four figures are uploaded one per file, in the order the manuscript cites "
               "them. The caption in the paper is NOT the legend; each legend below describes "
               "what the figure shows so it can be read on its own.\n")
    for name, caption, legend in figure_legends():
        doc.append("```text")
        doc.append("%s   File type: Figure" % name)
        doc.append("Title:  " + caption)
        doc.append("Legend: " + legend)
        doc.append("```\n")

    doc.append("### Section 2 — Supplemental Files (the three archives)\n")
    for name, kind, title, blurb in (
        ("source_main.zip", "LaTeX source file",
         "LaTeX source of the manuscript with its bibliography and the four cited figures",
         "LaTeX source used to typeset the manuscript. It holds the manuscript file, its "
         "BIB bibliography, the journal class file, and the four figure PDFs the manuscript "
         "cites. It typesets as it stands."),
        ("source_si.zip", "LaTeX source file",
         "LaTeX source of the supplementary information document and its bibliography",
         "LaTeX source used to typeset the supplementary information. It holds the supplement "
         "file, its BIB bibliography and the journal class file. It typesets as it stands."),
        ("source_code_and_results.zip", "data or code",
         "Analysis scripts, result files and figure generators behind every number and figure",
         "Every number, table and figure in the manuscript is read from a JSON result file "
         "produced by a script in this archive; no value is typed by hand. It holds the "
         "analysis and figure-generating scripts, the result files they write, the frozen "
         "benchmark snapshot and instrument catalogue they read, and an independent "
         "re-implementation of the point-pattern estimators used as a cross-check. The scripts "
         "run from the archive as it stands."),
    ):
        f = ARCHIVE_FACTS.get(name)
        if f:
            doc.append("### `%s` — %d files, %.0f KB\n" % (name, f["n"], f["kb"]))
        else:
            doc.append("### `%s`\n" % name)
        doc.append("**File type: %s** — Title is %d of the 200 characters:\n"
                   % (kind, len(title)))
        doc.append("```text")
        doc.append("Title:  " + title)
        doc.append("")
        doc.append("Legend: " + blurb)
        doc.append("```\n")

    doc.append("## Character handling\n")
    doc.append("Extracted from the PDF and normalised where a plain text box would not expect "
               "the character:\n")
    doc.append("- Abstract: %s" % changed_note(a_changed))
    doc.append("- Title: %s" % changed_note(t_changed))
    doc.append("")
    doc.append("The en dash in `2013-2026` and `Clark-Evans`, and the curly apostrophe in "
               "`year's`, are kept as they are: they are ordinary published typography and "
               "PeerJ uses them, so replacing them would alter the text rather than repair it. "
               "The minus sign is different — U+2212 is a mathematical operator rather than "
               "the keyboard hyphen, and a plain field can reject or mis-render it, so "
               "`-99 m per year` uses the ASCII hyphen-minus.\n")
    doc.append("Verify by eye against the manuscript's own abstract before pasting; this file "
               "is generated, so a change to the paper's abstract must be followed by "
               "`./build.sh` to regenerate it.\n")

    (OUT / "portal-fields.md").write_text("\n".join(doc) + "\n", encoding="utf-8")

    print("wrote %s" % (OUT / "portal-fields.md"))
    print("  title       %3d chars (limit %d)" % (len(title), TITLE_LIMIT))
    print("  short title %3d chars (limit %d)" % (len(SHORT_TITLE), SHORT_LIMIT))
    print("  abstract    %3d chars (limit %d), %d words, no linebreaks"
          % (len(abstract), ABSTRACT_LIMIT, len(abstract.split())))
    print("  abstract normalised: %d character(s) changed" % sum(a_changed.values()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
