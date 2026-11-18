PYTHON ?= python3
.PHONY: audit verify test paper figures audit-original audit-replacement verify-original verify-replacement
audit: audit-original audit-replacement
audit-original:
	$(PYTHON) -m artifact.audit --output results/recomputed
verify: verify-original verify-replacement
verify-original:
	$(PYTHON) -m artifact.audit --output results/recomputed --verify
test:
	$(PYTHON) -m unittest discover -s tests -v
paper:
	@test -f paper/main.tex || (echo "Paper source has not been added as paper/main.tex"; exit 1)
	cd paper && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex

figures:
	$(PYTHON) paper/build_figures.py

audit-replacement:
	$(PYTHON) -m artifact.study --study studies/model_replacement --output results/replacement
	$(PYTHON) -m artifact.supplement --study studies/model_replacement --output results/replacement
verify-replacement:
	$(PYTHON) -m artifact.study --study studies/model_replacement --output results/replacement --verify
	$(PYTHON) -m artifact.supplement --study studies/model_replacement --output results/replacement --verify
