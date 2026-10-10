MAIN = main

# BibTeX must run against an auxiliary file that already contains the citations.
# If the first LaTeX pass is interrupted, the .aux is incomplete, BibTeX reports
# "I found no \citation commands" and produces an empty .bbl (0 bytes) with no
# error — the bibliography silently disappears. Building twice is what prevents it.
all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex references.bib
	pdflatex -interaction=nonstopmode $(MAIN).tex
	pdflatex -interaction=nonstopmode $(MAIN).tex
	bibtex $(MAIN)
	pdflatex -interaction=nonstopmode $(MAIN).tex
	pdflatex -interaction=nonstopmode $(MAIN).tex
	@test -s $(MAIN).bbl || (echo "ERROR: empty .bbl — bibliography failed" && false)
	@echo "build ok: $$(pdfinfo $(MAIN).pdf | awk '/Pages/{print $$2}') pages, "\
"        $$(grep -c bibitem $(MAIN).bbl) references"

clean:
	rm -f $(MAIN).aux $(MAIN).bbl $(MAIN).blg $(MAIN).log $(MAIN).out $(MAIN).pdf

.PHONY: all clean
