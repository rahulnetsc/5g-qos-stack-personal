# Build the COMSNETS submission draft.
#
#   make          -> build/main.pdf via tectonic (self-contained)
#   make latexmk  -> same, using a local TeX Live installation
#   make clean

TECTONIC ?= tectonic
OUT  ?= build

.PHONY: all latexmk clean

all: $(OUT)/main.pdf

$(OUT)/main.pdf: main.tex refs.bib
	@mkdir -p $(OUT)
	$(TECTONIC) -X compile main.tex --outdir $(OUT)

latexmk:
	@mkdir -p $(OUT)
	latexmk -pdf -outdir=$(OUT) main.tex

clean:
	rm -rf $(OUT)
