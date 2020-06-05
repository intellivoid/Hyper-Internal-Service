# Some simple testing tasks (sorry, UNIX only).

PYXS = $(wildcard hyper_internal_service/*.pyx)
SRC = hyper_internal_service examples tests setup.py

all: test

.install-cython:
	pip install -r cython_requirements.txt
	touch .install-cython

hyper_internal_service/%.c: hyper_internal_service/%.pyx
	cython -3 -o $@ $< -I hyper_internal_service

cythonize: .install-cython $(PYXS:.pyx=.c)

.install-deps: cythonize $(shell find requirements -type f)
	pip install -r dev_requirements.txt
	@touch .install-deps


isort:
	isort -rc $(SRC)

flake: .flake

.flake: .install-deps $(shell find hyper_internal_service -type f)
	flake8 hyper_internal_service examples tests
	@if ! isort -c -rc hyper_internal_service tests examples; then \
            echo "Import sort errors, run 'make isort' to fix them!!!"; \
            isort --diff -rc hyper_internal_service tests examples; \
            false; \
	fi
	@if ! LC_ALL=C sort -c CONTRIBUTORS.txt; then \
            echo "CONTRIBUTORS.txt sort error"; \
	fi
	@touch .flake


flake8:
	flake8 $(SRC)

mypy: .flake
	mypy hyper_internal_service

isort-check:
	@if ! isort -rc --check-only $(SRC); then \
            echo "Import sort errors, run 'make isort' to fix them!!!"; \
            isort --diff -rc $(SRC); \
            false; \
	fi

check_changes:
	./tools/check_changes.py

.develop: .install-deps $(shell find hyper_internal_service -type f) .flake check_changes mypy
	# pip install -e .
	@touch .develop

test: .develop
	@pytest -q

vtest: .develop
	@pytest -s -v

cov cover coverage:
	tox

cov-dev: .develop
	@pytest --cov-report=html
	@echo "open file://`pwd`/htmlcov/index.html"

cov-ci-run: .develop
	@echo "Regular run"
	@pytest --cov-report=html

cov-dev-full: cov-ci-run
	@echo "open file://`pwd`/htmlcov/index.html"

clean:
	@rm -rf `find . -name __pycache__`
	@rm -f `find . -type f -name '*.py[co]' `
	@rm -f `find . -type f -name '*~' `
	@rm -f `find . -type f -name '.*~' `
	@rm -f `find . -type f -name '@*' `
	@rm -f `find . -type f -name '#*#' `
	@rm -f `find . -type f -name '*.orig' `
	@rm -f `find . -type f -name '*.rej' `
	@rm -f .coverage
	@rm -rf htmlcov
	@rm -rf build
	@rm -rf cover
	@python setup.py clean
	@rm -f hyper_internal_service/_frozenlist.html
	@rm -f hyper_internal_service/_frozenlist.c
	@rm -f hyper_internal_service/_frozenlist.*.so
	@rm -f hyper_internal_service/_frozenlist.*.pyd
	@rm -f hyper_internal_service/_http_parser.html
	@rm -f hyper_internal_service/_http_parser.c
	@rm -f hyper_internal_service/_http_parser.*.so
	@rm -f hyper_internal_service/_http_parser.*.pyd
	@rm -f hyper_internal_service/_multidict.html
	@rm -f hyper_internal_service/_multidict.c
	@rm -f hyper_internal_service/_multidict.*.so
	@rm -f hyper_internal_service/_multidict.*.pyd
	@rm -f hyper_internal_service/_websocket.html
	@rm -f hyper_internal_service/_websocket.c
	@rm -f hyper_internal_service/_websocket.*.so
	@rm -f hyper_internal_service/_websocket.*.pyd
	@rm -f hyper_internal_service/_parser.html
	@rm -f hyper_internal_service/_parser.c
	@rm -f hyper_internal_service/_parser.*.so
	@rm -f hyper_internal_service/_parser.*.pyd
	@rm -rf .tox
	@rm -f .develop
	@rm -f .flake
	@rm -f .install-deps
	@rm -rf hyper_internal_service.egg-info

install:
	@pip install -U 'pip'
	@pip install -Ur dev_requirements.txt

.PHONY: all build flake test vtest cov clean doc mypy
