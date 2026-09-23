PYTHON ?= python

.PHONY: test diagnostics run verify
test:
	$(PYTHON) -m pytest -q

diagnostics:
	PYTHONPATH=src $(PYTHON) -m warehouse_control.cli diagnostics

run:
	PYTHONPATH=src $(PYTHON) -m uvicorn warehouse_control.api:app --host 127.0.0.1 --port 8000

verify:
	$(PYTHON) scripts/verify_repo.py
