.PHONY: coverage setup test

coverage:
	poetry run coverage run -m unittest discover -s tests
	poetry run coverage xml --quiet
	poetry run coverage report --show-missing

lint:
	poetry run pre-commit run -a

# in CI we use a github action; this is for local
# you may need to add ~/.local/bin to your PATH to find it
prerequisites:
	python3 -m pip install -U poetry

setup:
	poetry config virtualenvs.in-project true
	poetry install
	poetry run pre-commit install

test:
	poetry run python3 -m unittest discover -s tests
