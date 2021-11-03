SHELL := /bin/bash
.ONESHELL:

.PHONY: all serve publicserve

all:
	. venv/bin/activate
	./process_pages.py

serve:
	. venv/bin/activate
	./serve.sh

watch:
	. venv/bin/activate
	./watch.sh

publicserve:
	. venv/bin/activate
	python -m http.server 7007 --bind 0.0.0.0 --directory htdocs
