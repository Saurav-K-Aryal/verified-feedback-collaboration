PYTHON ?= python3
.PHONY: audit verify test paper figures
audit:
	$(PYTHON) -m artifact.audit --output results/recomputed
verify:
	$(PYTHON) -m artifact.audit --output results/recomputed --verify
test:
	$(PYTHON) -m unittest discover -s tests -v
paper:
	@test -f paper/main.tex || (echo "Paper source has not been added as paper/main.tex"; exit 1)
	cd paper && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex

figures:
	$(PYTHON) paper/build_figures.py
