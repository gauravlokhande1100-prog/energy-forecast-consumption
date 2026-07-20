# lecture/Makefile -- single entry point for render and qmd->ipynb conversion.
# Run from this directory.
#
# QUARTO_PYTHON is consulted only by `render` and `preview` (Quarto needs to
# execute the chapters' Python code). `notebooks` calls `quarto convert`,
# which is a pure syntax transform and does not need a Python interpreter.
#
# Set QUARTO_PYTHON in the environment (export, direnv, or per-call) before
# `make render` / `make preview`. There is no default -- a stale default would
# only cause Quarto to print a misleading warning on every invocation.

QMD_SOURCES   := $(filter-out references.qmd,$(wildcard *.qmd))
IPYNB_OUTPUTS := $(QMD_SOURCES:.qmd=.ipynb)

.PHONY: help render preview notebooks clean-notebooks clean-freeze check-python

help:
	@echo "Targets: render | preview | notebooks | clean-notebooks | clean-freeze"
	@echo "QUARTO_PYTHON = $${QUARTO_PYTHON:-(unset; required for render/preview)}"

check-python:
	@if [ -z "$$QUARTO_PYTHON" ]; then \
		echo "ERROR: QUARTO_PYTHON is not set. Export it to your venv's python3, e.g."; \
		echo "  export QUARTO_PYTHON=\$$HOME/workspace/Lehre.d/ddmo-sose-26/.venv/bin/python3"; \
		exit 1; \
	fi
	@if [ ! -x "$$QUARTO_PYTHON" ]; then \
		echo "ERROR: QUARTO_PYTHON='$$QUARTO_PYTHON' is not an executable file."; \
		exit 1; \
	fi

render: check-python
	quarto render

preview: check-python
	quarto preview

notebooks: $(IPYNB_OUTPUTS)
	@echo "Generated $(words $(IPYNB_OUTPUTS)) notebooks."

%.ipynb: %.qmd
	quarto convert $<

clean-notebooks:
	rm -f $(IPYNB_OUTPUTS)

clean-freeze:
	rm -rf _freeze .quarto
