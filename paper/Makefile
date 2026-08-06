# Build the COMSNETS submission draft.
#
#   make           -> main.pdf via tectonic (self-contained). main.pdf is
#                     committed, so the draft reads without a TeX setup.
#   make latexmk   -> same, using a local TeX Live installation
#   make clean     -> drop the build tree, keep main.pdf
#   make distclean -> drop main.pdf too

TECTONIC ?= tectonic
OUT  ?= build

.PHONY: all latexmk clean distclean

# main.pdf is committed so the draft can be read without a TeX toolchain.
all: main.pdf

main.pdf: $(OUT)/main.pdf
	cp $(OUT)/main.pdf $@

$(OUT)/main.pdf: main.tex refs.bib
	@mkdir -p $(OUT)
	$(TECTONIC) -X compile main.tex --outdir $(OUT)

latexmk:
	@mkdir -p $(OUT)
	latexmk -pdf -outdir=$(OUT) main.tex
	cp $(OUT)/main.pdf main.pdf

# Drops the build tree but keeps the committed main.pdf.
clean:
	rm -rf $(OUT)

# Drops the committed PDF too.
distclean: clean
	rm -f main.pdf
