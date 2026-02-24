.PHONY: help install test test-quick test-cov lint format check pre-push clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies and setup pre-commit hooks
	pip install -r requirements.txt
	pre-commit install --hook-type pre-commit
	@echo "✅ Installation complete!"

test:  ## Run all tests
	pytest tests/ -v

test-quick:  ## Run tests (failed + changed only)
	pytest tests/ -x --lf -v

test-cov:  ## Run tests with coverage report
	pytest tests/ --cov=app --cov-report=html --cov-report=term-missing:skip-covered --cov-fail-under=70
	@echo "\n📊 Coverage report generated: htmlcov/index.html"

lint:  ## Check code style with ruff
	ruff check .

format:  ## Format code with ruff
	ruff format .

check: lint test-cov  ## Run all checks (lint + tests + coverage)
	@echo "\n✅ All checks passed!"

pre-push: check  ## Validate before pushing (full check)
	@echo "\n✅ Ready to push!"
	@echo "Run: git push"

clean:  ## Clean cache files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage .ruff_cache
	@echo "✅ Cache cleaned!"
