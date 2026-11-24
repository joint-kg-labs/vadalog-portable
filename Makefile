PY ?= python3
VENV = .venv
BIN = $(VENV)/bin

.PHONY: venv test lint clean examples check-python ui pyz binary smoke dist

# The engine needs no installation at all: ./vadalog runs it from this
# directory.  The venv exists so that `pytest` is available for `make test`.

venv:
	@$(PY) -m venv $(VENV) || { \
	  echo "could not create a virtualenv."; \
	  echo "  macOS:          install Python 3.9+ from python.org or Homebrew"; \
	  echo "  Debian/Ubuntu:  apt install python3-venv"; \
	  echo "  or skip it entirely and use ./vadalog"; exit 1; }
	@$(BIN)/python -m pip install --quiet --upgrade pip setuptools wheel \
	  || echo "note: could not upgrade pip; falling back to a plain install"
	@$(BIN)/python -m pip install --quiet -e ".[dev]" \
	  || $(BIN)/python -m pip install --quiet ".[dev]" \
	  || { echo "install failed; use ./vadalog and run pytest yourself"; exit 1; }
	@echo "ready: source $(VENV)/bin/activate"

test: | $(VENV)
	$(BIN)/python -m pytest -q

lint: | $(VENV)
	$(BIN)/python -m compileall -q src/vadalog

examples:
	@for f in examples/*.vada; do echo "== $$f"; ./vadalog run $$f || exit 1; done

ui:
	./vadalog ui

# The single-file distribution: one 80 KB archive that any Python 3.9+ runs
# directly, with no installation.  This is what a release ships.
pyz:
	@$(PY) tools/build_pyz.py
	@$(PY) tools/smoke.py --skip-ui -- $(PY) dist/vadalog.pyz

# The native build, for a machine with no Python at all: the same tree, frozen
# together with an interpreter.  PyInstaller is a build-time tool only, and one
# build makes one executable, for this machine; a release carries five, built
# one per runner by .github/workflows/binaries.yml.
binary:
	@$(PY) tools/build_binary.py
	@$(PY) tools/smoke.py --skip-ui -- dist/vadalog

# Everything a recipient would do with a finished build, the web UI included.
# Point it at whatever you built:  make smoke BUILD="dist/vadalog"
BUILD ?= $(PY) dist/vadalog.pyz
smoke:
	@$(PY) tools/smoke.py -- $(BUILD)

# The usual sdist + wheel, for anyone who does have pip.
dist: | $(VENV)
	$(BIN)/python -m pip install --quiet --upgrade build
	$(BIN)/python -m build

check-python:
	@$(PY) -c "import sys; print('python', '.'.join(map(str, sys.version_info[:3])))"
	@$(PY) -m pip --version 2>/dev/null || echo "pip not available for $(PY)"

$(VENV):
	$(MAKE) venv

clean:
	rm -rf $(VENV) build dist *.egg-info .pytest_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
