# Build the talk deck.
#
#   make       -> two-tier-scheduler.pptx (and .pdf, if LibreOffice is around)
#   make pdf   -> the PDF only
#   make clean -> drop both artefacts
#
# python-pptx is not a project dependency (the deck is not part of the
# simulator), so this deliberately uses the system interpreter rather than the
# uv venv:  pip install --user python-pptx
#
# Both artefacts are committed so the deck can be read without either tool.

PYTHON ?= python3
SOFFICE ?= soffice

.PHONY: all pdf clean

all: two-tier-scheduler.pdf

two-tier-scheduler.pptx: build_deck.py
	cd .. && $(PYTHON) deck/build_deck.py

pdf: two-tier-scheduler.pdf

# LibreOffice writes alongside the input; it has no way to name the output.
two-tier-scheduler.pdf: two-tier-scheduler.pptx
	$(SOFFICE) --headless --convert-to pdf two-tier-scheduler.pptx

clean:
	rm -f two-tier-scheduler.pptx two-tier-scheduler.pdf
