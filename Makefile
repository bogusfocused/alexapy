# SPDX-License-Identifier: Apache-2.0
# Based on code from https://github.com/bachya/simplisafe-python/blob/dev/Makefile
coverage:
	#Not implemented yet
	#pipenv run py.test -s --verbose --cov-report term-missing --cov-report xml --cov=alexapy tests
bump:
	pipenv run semantic-release release
	pipenv run semantic-release changelog
bump_and_publish:
	pipenv run semantic-release publish --noop
	pipenv run semantic-release changelog
clean:
	rm -rf dist/ build/ .egg alexapy.egg-info/
init:
	pip3 install pip pipenv
	pipenv lock
	pipenv install --three --dev
lint: flake8 docstyle pylint typing
flake8:
	pipenv run flake8 alexapy
docstyle:
	pipenv run pydocstyle alexapy
pylint:
	pipenv run pylint alexapy
publish:
	pipenv run python setup.py sdist bdist_wheel
	pipenv run twine upload dist/*
	rm -rf dist/ build/ .egg alexapy.egg-info/
test:
	#Not implemented yet
	#pipenv run py.test
typing:
	pipenv run mypy --ignore-missing-imports alexapy
