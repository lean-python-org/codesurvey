.PHONY: deps example test mypy lint check docs-serve docs-build docs-github

deps:
	poetry install

example:
	poetry run python -m examples.basic

lint:
	poetry run flake8
mypy:
	poetry run mypy --show-error-codes codesurvey
	poetry run mypy --show-error-codes examples
test:
	poetry run pytest \
		--cov="codesurvey" \
		--cov-report="html:tests/coverage" \
		--cov-report=term
check: lint mypy test

docs-serve:
	poetry run mkdocs serve
docs-build:
	poetry run mkdocs build
docs-github:
	poetry run mkdocs gh-deploy
