.PHONY: install all pipeline test dashboard clean
install:
	pip install -r requirements.txt
pipeline:
	python -m pipeline.run
test:
	pytest -q
all: pipeline test
dashboard:
	streamlit run dashboards/app.py
clean:
	rm -rf lake warehouse logs
