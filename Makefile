.PHONY: install test bench quick
install:
	pip install -e ".[dev]"
test:
	pytest -q -m "not slow"
quick:
	aisleopt bench --quick --out outputs
bench:
	aisleopt bench --out outputs
