#!/usr/bin/env python3
"""make_peerj_cover.py -- write the Author Cover Page as the manuscript's first page.

WHY THIS CHANGED, 2026-10-11. This script used to build `peerj-cover.tex` as a SEPARATE
document, uploaded as `3_author_cover_page.pdf`, on the reasoning that folding the cover into
the manuscript "would put author contact details into the version of record". That reasoning was
an inference, and it was WRONG. PeerJ's own template says the opposite, in its own words:

    "Please do not submit this one-page document. Your cover page must be included in your
     main manuscript. Copy and paste the above text into the first page of your manuscript and
     then replace the text with your author information."

and the portal's Manuscript slot repeats it: "Include Author Cover Page (view example)" -- the
example being that template. Two of PeerJ's own artefacts agree, so the separate-document
design is abandoned.

WHAT THE TEMPLATE ASKS FOR: Manuscript Title; authors; their affiliations; the Corresponding
Author with a street address, city, state, zip and country; and the e-mail address. `wlpeerj`'s
own \\maketitle already prints the title, the authors, the affiliations, the corresponding
author and the e-mail, so the cover page needs to add only what the class does not: the
corresponding author's postal address, and the statements a cover page is expected to carry
that do not belong in the body (originality and prior dissemination).

NO STREET ADDRESS IS INVENTED. Nothing in this project records one -- checked, and the only
matches for "street"/"postal"/"zip" anywhere are the word "streets" in prose. The template
leaves that line as a placeholder, so a clearly-marked placeholder is emitted here for the
author to fill rather than a fabricated address, which would be a false statement about a real
person.

EVERY VALUE IS READ, NOT RETYPED. The title, authors, affiliations and corresponding e-mail are
parsed out of the generated `peerj-main.tex`, so the cover page cannot contradict the
manuscript.

USAGE
    python3 make_peerj_cover.py            # writes ../PeerJ/peerj-cover.tex
"""
from __future__ import annotations

import pathlib
import re
import sys

from paper_source import abstract_word_count, ADDRESS

HERE = pathlib.Path(__file__).resolve().parent
# The submission folder is this file's parent: it holds the generated documents, and
# `source/` holds the generators. Resolved from the file's own location so the tree builds
# wherever it is checked out.
OUT = HERE.parent



def grab_all(tex: str, name: str) -> list[str]:
    return re.findall(r"\\" + name + r"(?:\[[^\]]*\])?\{([^}]*)\}", tex)


def main() -> int:
    main_tex = (OUT / "peerj-main.tex")
    if not main_tex.exists():
        print("REFUSING: %s not found. Run convert_to_peerj.py first." % main_tex)
        return 1
    tex = main_tex.read_text()

    title = " ".join(re.sub(r"\s+", " ", grab_all(tex, "title")[0]).split())
    authors = [re.sub(r"\s+", " ", a).strip() for a in grab_all(tex, "author")]
    affils = [re.sub(r"\s+", " ", a).strip() for a in grab_all(tex, "affil")]
    corr = re.search(r"\\corrauthor(?:\[[^\]]*\])?\{([^}]*)\}\{([^}]*)\}", tex)
    if not (title and authors and affils and corr):
        print("REFUSING: could not parse title/authors/affiliations/corresponding author")
        return 1
    corr_name, corr_mail = corr.group(1).strip(), corr.group(2).strip()

    # The abstract's word count, reported so the cover page can state it.
    #
    # This number was WRONG. It was 197 while `portal-values.md` said 198 for the same
    # abstract, and the rendered PDF holds 199 words, so neither document was right and the
    # two disagreed with each other. The old expression also substituted for `\SI` without
    # keeping either argument, which is where "197" came from.
    #
    # The count is now taken by one function, `abstract_word_count`, which this script and
    # `make_peerj_bundle.py` both import, so the cover page, the portal values and the
    # bundle cannot state three different lengths for one abstract.
    abstract_words = abstract_word_count(tex)

    # Author and affiliation lines are built HERE, not inside the f-string below.
    # Two reasons: a `\\` line break inside an f-string is a syntax error on Python 3.9
    # (this environment), and joining on a bare newline would let LaTeX collapse the
    # entries onto one line -- which is exactly what the first build did.
    #
    # The separator is `\enspace`, NOT a literal U+2003 em-space. A raw Unicode space
    # reached the .tex and pdfLaTeX refused it eight times ("Unicode character (U+2003)")
    # while still producing a PDF, so the page looked right and the build was broken.
    authors_block = "\\\\\n".join("%d.\\enspace %s" % (i + 1, a)
                                  for i, a in enumerate(authors))
    affils_block = "\\\\\n".join("%d.\\enspace %s" % (i + 1, a)
                                 for i, a in enumerate(affils))

    # THE COVER CONTENT, AS A FRAGMENT THAT GOES INSIDE THE MANUSCRIPT.
    #
    # A fragment, not a document: no \documentclass, no \begin{document}. The converter splices
    # it in immediately after \maketitle, so it lands on the manuscript's FIRST PAGE, which is
    # what PeerJ's template instructs. wlpeerj's \maketitle has already printed the title, the
    # authors, the affiliations and the corresponding author's e-mail, so this adds only what
    # the class does not: the postal address the template asks for, and the statements a cover
    # page carries that do not belong in the body. Repeating the title and the author list would
    # print them twice on one page.
    body = f"""% AUTO-GENERATED by source/make_peerj_cover.py - do not edit by hand.
% PeerJ Author Cover Page content. Spliced into the manuscript's first page by
% convert_to_peerj.py, as PeerJ's own template instructs: "Your cover page must be
% included in your main manuscript ... the first page of your manuscript".
% NOTE: no \\thispagestyle here -- the converter splices this immediately after the
% manuscript's own \\thispagestyle{{empty}}, and a second one only duplicates it.

\\noindent\\textbf{{Corresponding author's postal address}}\\\\
{corr_name}\\\\
{ADDRESS}

\\medskip
\\noindent\\textbf{{Article type}}\\\\
Research Article (Standard Sections). Abstract length: {abstract_words} words.

\\medskip
\\noindent\\textbf{{Statement of originality and prior dissemination}}\\\\
This manuscript is original, is not under consideration elsewhere, and has not been
published previously in whole or in part. No part of this work has appeared in a conference
proceedings or a book chapter.

\\medskip
\\noindent\\textbf{{Use of generative AI}}\\\\
Declared in full in the manuscript's Generative AI Use Disclosure Statement, in accordance
with PeerJ's Generative AI policy: the tool, its version, how it was used, and the authors'
confirmation of originality, of the tool's terms of use, and of responsibility for the whole
content.

\\medskip
\\noindent\\textbf{{Data and code availability}}\\\\
Raw third-party observations, and all derived data, models and analysis scripts, are openly
available under CC BY 4.0 at the DOI given in the manuscript's Data Availability statement,
and are also provided as Supplemental Information.

\\vspace{{\\baselineskip}}
"""
    path = OUT / "peerj-cover.tex"
    path.write_text(body)

    # A GUARD, because this defect produced a correct-looking PDF from a broken build.
    # pdfLaTeX rejects a raw non-ASCII character with an "! LaTeX Error" and then carries
    # on, so the page rendered and only the log showed the problem. Any non-ASCII byte in
    # the generated source is refused here instead.
    bad = sorted({c for c in body if ord(c) > 127})
    if bad:
        print("REFUSING: non-ASCII in the generated source: %s"
              % ", ".join("U+%04X" % ord(c) for c in bad))
        return 1

    print("wrote %s" % path)
    print("  title   : %s" % title[:64])
    print("  authors : %d, affiliations: %d" % (len(authors), len(affils)))
    print("  corr.   : %s <%s>" % (corr_name, corr_mail))
    print("  checks  : ASCII only (pdfLaTeX-safe)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
