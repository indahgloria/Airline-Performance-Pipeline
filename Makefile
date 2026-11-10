.PHONY: setup fake real ingest transform report status docs clean

setup:            ## create venv + install (use Python 3.12; dbt doesn't support 3.14 yet)
	python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt

fake:             ## full pipeline on fake data
	python -m pipeline run --source fake --months 2025-01:2025-03

real:             ## full pipeline on real BTS data
	python -m pipeline run --source real --months 2025-01:2025-03

ingest:
	python -m pipeline ingest

transform:
	python -m pipeline transform

report:
	python -m pipeline report

status:
	python -m pipeline status

docs:             ## dbt lineage graph in your browser
	cd transform && dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir .

clean:
	rm -rf data reports transform/target transform/logs
