# logilens — developer shortcuts.  `make help` lists the targets.

PYTHON ?= python3
VENV   ?= .venv
PY     := $(VENV)/bin/python
PIP    := $(PY) -m pip
APP    := $(VENV)/bin/logilens

.DEFAULT_GOAL := help
.PHONY: help venv install-dev test test-fast lint espresso helper build release install-local clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[1m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

$(PY):
	$(PYTHON) -m venv $(VENV)

venv: $(PY) ## Create the .venv virtualenv (PYTHON=python3.x to choose the interpreter)

install-dev: $(PY) ## Editable install with dev extras (pytest, ruff)
	$(PIP) install --upgrade pip
	$(PIP) install -e '.[dev]'

test: ## Run the whole test suite (Java tests skip without Java + logisim.jar)
	$(PY) -m pytest tests -q

test-fast: ## Run the tests that do not need Java
	$(PY) -m pytest tests -q -m "not java"

lint: ## Ruff static checks
	$(VENV)/bin/ruff check src tests

espresso: ## Build the vendored Espresso into the user cache
	$(PY) -c 'from logilens.env.espresso_build import build_espresso; r = build_espresso(); \
	print(r.binary if r.ok else r.log); raise SystemExit(0 if r.ok else 1)'

helper: ## Compile the Java helper against the located logisim.jar (into the user cache)
	$(PY) -c 'import sys; from logilens.backends.java.locate import find_jar; \
	from logilens.backends.java.build import build_helper; jar = find_jar(); \
	sys.exit("logisim.jar not found (set LOGISIM_JAR)") if jar is None else print(build_helper(jar, force=True))'

build: ## Build sdist + wheel into dist/ and print their sha256
	PYTHON=$(PY) scripts/release.sh --build-only

release: ## Release build: checks the version, runs fast tests, builds, prints the formula stanza
	PYTHON=$(PY) scripts/release.sh

install-local: ## Install for the current user without Homebrew (scripts/install.sh)
	bash scripts/install.sh

clean: ## Remove build/, dist/ and caches (never touches sources)
	rm -rf build dist .pytest_cache .ruff_cache
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +
	find src -maxdepth 2 -type d -name '*.egg-info' -prune -exec rm -rf {} +
