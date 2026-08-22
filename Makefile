.PHONY: run test eval schema apps-script lint

run:            ## start the registry at http://localhost:8000
	.venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000

test:           ## run the full pytest suite
	.venv/bin/pytest -q

eval:           ## extraction accuracy vs golden cases (needs GROQ_API_KEY)
	.venv/bin/python harness/run_eval.py

schema:         ## regenerate src/schema.py from specs/data_dictionary.yaml
	.venv/bin/python scripts/generate_schema.py

apps-script:    ## regenerate the Google Apps Script backend
	.venv/bin/python scripts/setup_apps_script.py

lint:
	.venv/bin/ruff check src tests harness scripts
