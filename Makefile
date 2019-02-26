# SPDX-License-Identifier: Apache-2.0
# Based on code from https://github.com/bachya/simplisafe-python/blob/dev/Makefile
coverage:
	#Not implemented yet
	#pipenv run py.test -s --verbose --cov-report term-missing --cov-report xml --cov=alexapy tests
clean:
	rm -rf dist/ build/ .egg alexapy.egg-info/
init:
	pip3 install pip pipenv
	pipenv lock
	pipenv install --three --dev
lint:
	pipenv run flake8 alexapy
	pipenv run pydocstyle alexapy
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
