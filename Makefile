# run `make init`, then use the other targets
# didn't want to depend on init since it takes a while

.PHONY: typecheck
typecheck:
	venv/bin/mypy *.py

.PHONY: lint
lint:
	venv/bin/black *.py

#.PHONY: test
#test: lint
#	venv/bin/python -m unittest *py

.PHONY: init
init: virtualenv

.PHONY: virtualenv
virtualenv: venv/bin/activate
	venv/bin/pip install -U pip
	venv/bin/pip install mypy black

venv/bin/activate:
	which virtualenv || pip install virtualenv
	python -m virtualenv venv
	echo '*' > venv/.gitignore

.PHONY: clean
clean:
	deactivate || true
	rm -rf .mypy_cache __pycache__ venv
