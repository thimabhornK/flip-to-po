.PHONY: help install data demo eval sweep test api clean

PYTHON ?= python
export PYTHONPATH := src

help:
	@echo "Targets:"
	@echo "  install   Install runtime + dev dependencies"
	@echo "  data      Generate the synthetic dataset and trusted sources"
	@echo "  demo      Run the end-to-end CLI demo (3 representative requisitions)"
	@echo "  eval      Run the evaluation harness (writes eval/results.json)"
	@echo "  sweep     Sweep the auto-flip threshold (writes eval/sweep.json)"
	@echo "  test      Run the test suite"
	@echo "  api       Start the FastAPI server (http://127.0.0.1:8000/docs)"
	@echo "  clean     Remove generated data and caches"

install:
	$(PYTHON) -m pip install -e ".[dev]"

data:
	$(PYTHON) scripts/generate_synthetic_data.py

demo: data
	$(PYTHON) scripts/demo.py

eval: data
	$(PYTHON) -m eval.harness

sweep: data
	$(PYTHON) -m eval.sweep

test:
	$(PYTHON) -m pytest

api: data
	$(PYTHON) -m uvicorn flip_to_po.api.app:app --reload

clean:
	rm -rf data/synthetic eval/results.json eval/sweep.json
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -prune -exec rm -rf {} +
