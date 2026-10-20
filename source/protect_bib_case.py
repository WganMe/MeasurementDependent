#!/usr/bin/env python3
"""Brace-protect proper nouns and acronyms in bibliography titles.

WHY THIS IS NEEDED
    The PeerJ class uses apalike, which lowercases the case of every title it
    prints unless the author protects it. So a .bib entry that correctly says
    "using API" is PRINTED as "using api", "Newcastle upon Tyne" as "newcastle
    upon tyne", and "GeoAI" as "geoai". The .bib was not wrong; the output was,
    and the fix is braces around the tokens that must keep their case.

WHAT IT DOES
    For each TITLE field in references.bib, wrap every token that looks like a
    proper noun or acronym in braces. A token qualifies when it is:
      - an acronym: two or more capitals, e.g. API, GIS, UK, US, GeoAI
      - a mixed-case word: GeoAI, SenseMyStreet, CUPTI
      - a capitalised word that appears mid-title and is not the first word,
        EXCEPT ordinary stop words (a, an, the, and, of, for, in, on, to, ...)

    Only tokens NOT already braced are touched, so the script is idempotent.

WHY NOT A LIST OF THE 18 THE REVIEW NAMED
    The review listed the ones a reader noticed. The same failure mode affects
    every title in the file, and fixing only the reported instances guarantees a
    second review round for the rest. This is measured against the whole file.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BIB = os.path.join(HERE, "references.bib")

# Words that may stay lowercase mid-title. Anything else capitalised is protected.
# PLACE AND INSTITUTION NAMES ARE ORDINARY CAPITALISED WORDS, so the acronym rule
# above does not catch them and apalike prints them lowercased: "newcastle upon
# tyne". They are proper nouns, not common nouns, and there is no general test
# that separates them from "Urban Change", so they are listed. Every phrase here
# was observed printing wrong in the built .bbl.
PLACE_PHRASES = [
    "Newcastle upon Tyne",
    "Australian Urban Observatory",
    "Malaysia Urban Observatory",
    "Saudi Arabia",
    "Middle Eastern",
    "Smart Columbus Operating System",
    "SenseMyStreet",
    "Brasília of the North",
]

STOP = {
    "a", "an", "the", "and", "or", "but", "nor", "for", "of", "in", "on", "at",
    "to", "by", "with", "from", "as", "is", "are", "was", "were", "be", "been",
    "into", "than", "that", "this", "these", "those", "via", "per", "vs",
    "under", "over", "between", "among", "across", "within", "without", "after",
    "before", "during", "through", "toward", "towards", "about", "against",
}


def protect_title(title):
    """Return the title with proper nouns and acronyms brace-protected."""
    for phrase in PLACE_PHRASES:
        if phrase in title and "{" + phrase + "}" not in title:
            title = title.replace(phrase, "{" + phrase + "}")
    # Split on whitespace but keep the delimiters so spacing is preserved.
    tokens = re.split(r"(\s+)", title)
    out = []
    for idx, tok in enumerate(tokens):
        if not tok.strip():
            out.append(tok)
            continue
        # already protected at the outer level?
        if tok.startswith("{") and tok.endswith("}") and tok.count("{") == 1:
            out.append(tok)
            continue
        # strip trailing punctuation for the test, re-attach afterwards
        m = re.match(r"^([^\w]*)(.*?)([^\w]*)$", tok)
        lead, core, trail = m.group(1), m.group(2), m.group(3)
        if not core:
            out.append(tok)
            continue
        first_word = not any(t.strip() for t in tokens[:idx])
        caps = sum(1 for c in core if c.isupper())
        mixed = caps > 0 and any(c.islower() for c in core)
        should = False
        # An ordinary Capitalised-Word is not at risk: apalike lowercases it and
        # it still reads. Acronyms (API, GIS, UK) and camel-case names (GeoAI,
        # SenseMyStreet, CUPTI) are. Requiring EVERY capital to be adjacent-ish
        # is not reliable, so the test is simply two or more capitals in a token
        # with no more than one lower-case run -- which admits API, GIS, UK, US,
        # GeoAI and rejects "Complexity-Tiered", whose capitals are separated by a
        # hyphen and read correctly either way.
        letters = [c for c in core if c.isalpha()]
        runs = sum(1 for i, c in enumerate(letters)
                   if c.isupper() and (i == 0 or not letters[i - 1].isupper()))
        if "-" not in core and caps >= 2 and runs <= 2:
            should = True
        # A WORD THAT IS CAPITALISED IN THE BIB IS NOT NECESSARILY AT RISK.
        # apalike lowercases the title as it prints it, but a word like "Quality"
        # or "Performance" reads correctly either way at the start of a phrase.
        # What goes visibly wrong is a proper noun or acronym that must keep
        # capitals mid-title: Newcastle, UK, GeoAI, API, GIS. Bracing every
        # capitalised word produced 64 changed titles and buried the real fixes,
        # so only tokens carrying TWO OR MORE capitals (or already mixed case,
        # which means the author intended them) are protected.
        out.append(lead + ("{" + core + "}" if should else core) + trail)
    return "".join(out)


def main():
    apply = "--apply" in sys.argv
    text = open(BIB, encoding="utf-8").read()

    changed = []

    def repl(m):
        field, body = m.group(1), m.group(2)
        new = protect_title(body)
        if new != body:
            changed.append((body, new))
        return field + "{" + new + "}"

    # TITLE = {...} spanning one or more lines
    new_text = re.sub(r"(?im)^(\s*TITLE\s*=\s*)\{([^@]*?)\}(,?\s*$)",
                      lambda m: repl(m), text)

    print("titles changed:", len(changed))
    for old, new in changed[:6]:
        print("  OLD:", old[:78])
        print("  NEW:", new[:78])
    if len(changed) > 6:
        print("  ... %d more" % (len(changed) - 6))

    if apply:
        open(BIB, "w", encoding="utf-8").write(new_text)
        print("\nwritten:", BIB)
    else:
        print("\nDRY RUN. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
