PYTHON ?= python3
BUILD_DIR ?= build/release

RUFF_PATHS := src tests scripts user-inference-v0/src user-inference-v0/tests user-inference-v0/scripts user-inference-v0.1/src user-inference-v0.1/tests user-inference-v0.1/scripts

.PHONY: help setup setup-core setup-v0 setup-v01 metadata docs-check lint test test-core test-v0 test-v01 smoke smoke-v0 smoke-v01 build package-check check

help:
	@echo "DJR-MCP Finder contributor commands"
	@echo "  make setup          Install all three development packages (Python 3.12+)"
	@echo "  make test           Run core, formal V0, and V0.1 candidate tests"
	@echo "  make lint           Run critical Ruff correctness checks"
	@echo "  make smoke          Validate both inference bundles without model downloads"
	@echo "  make build          Build wheel and sdist for all three distributions"
	@echo "  make package-check  Build and validate metadata plus artifact contents"
	@echo "  make check          Run the complete local CI-equivalent gate"

setup:
	@$(PYTHON) -c 'import sys; assert sys.version_info >= (3, 12), "make setup requires Python 3.12+"'
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]" -e "./user-inference-v0[dev]" -e "./user-inference-v0.1[dev]"

setup-core:
	$(PYTHON) -m pip install -e ".[dev]"

setup-v0:
	$(PYTHON) -m pip install -e "./user-inference-v0[dev]"

setup-v01:
	@$(PYTHON) -c 'import sys; assert sys.version_info >= (3, 12), "V0.1 candidate requires Python 3.12+"'
	$(PYTHON) -m pip install -e "./user-inference-v0.1[dev]"

metadata:
	$(PYTHON) scripts/check_project_metadata.py

docs-check:
	$(PYTHON) scripts/check_documentation.py

lint:
	$(PYTHON) -m ruff check --select E9,F63,F7,F82 $(RUFF_PATHS)

test-core:
	$(PYTHON) -m pytest -q tests

test-v0:
	$(PYTHON) -m pytest -q user-inference-v0/tests

test-v01:
	$(PYTHON) -m pytest -q user-inference-v0.1/tests

test: test-core test-v0 test-v01

smoke-v0:
	djrmcp-predict validate-fasta user-inference-v0/examples/synthetic_example.faa
	djrmcp-predict model-info

smoke-v01:
	djrmcp-predict-v01 validate-fasta user-inference-v0.1/examples/synthetic_example.faa
	djrmcp-predict-v01 model-info

smoke: smoke-v0 smoke-v01

build: metadata
	mkdir -p "$(BUILD_DIR)/root" "$(BUILD_DIR)/formal-v0" "$(BUILD_DIR)/candidate-v01"
	$(PYTHON) -m build --outdir "$(BUILD_DIR)/root" .
	$(PYTHON) -m build --outdir "$(BUILD_DIR)/formal-v0" user-inference-v0
	$(PYTHON) -m build --outdir "$(BUILD_DIR)/candidate-v01" user-inference-v0.1

package-check: build
	$(PYTHON) -m twine check $(BUILD_DIR)/*/*
	$(PYTHON) scripts/check_distribution_artifacts.py --artifact-root "$(BUILD_DIR)"

check: metadata docs-check lint test smoke package-check
