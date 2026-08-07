# Build the talk deck.
#
#   make       -> two-tier-scheduler.pptx (and .pdf, if LibreOffice is around)
#   make pdf   -> the PDF only
#   make clean -> drop both artefacts
#
# python-pptx and pillow are not project dependencies (the deck is not part of
# the simulator), so this deliberately uses the system interpreter rather than
# the uv venv:  pip install --user python-pptx pillow
#
# Equations are typeset by tectonic and converted by pdftocairo, then cached in
# eq/. Those PNGs are committed, so LaTeX is needed only when the mathematics
# itself changes. Both output artefacts are committed too, so the deck can be
# read without any of this.

PYTHON ?= python3
SOFFICE ?= soffice

.PHONY: all pdf clean distclean

all: two-tier-scheduler.pdf

two-tier-scheduler.pptx: build_deck.py $(wildcard eq/*.png)
	cd .. && $(PYTHON) deck/build_deck.py

pdf: two-tier-scheduler.pdf

# LibreOffice writes alongside the input; it has no way to name the output.
two-tier-scheduler.pdf: two-tier-scheduler.pptx
	$(SOFFICE) --headless --convert-to pdf two-tier-scheduler.pptx

clean:
	rm -f two-tier-scheduler.pptx two-tier-scheduler.pdf

# Also drops the typeset equations, forcing a LaTeX round trip on the next build.
distclean: clean
	rm -rf eq
