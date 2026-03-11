.PHONY: all \
	framework-pdf validate-model analyze-routes show-barriers rank-feasibility run-scenarios generate-diagrams export-public-data build-dashboard start-web-server clean \
	paper check analyze barriers feasibility scenarios diagrams export dashboard serve

TEX_FILE := village_governance_technical_framework_nepal.tex
BUILD_DIR := build
WEB_HOST ?= 127.0.0.1
WEB_PORT ?= 8000

all:
	@echo "Primary targets: framework-pdf, validate-model, analyze-routes, show-barriers, rank-feasibility, run-scenarios, generate-diagrams, export-public-data, build-dashboard, start-web-server, clean"
	@echo "Compatibility aliases: paper, check, analyze, barriers, feasibility, scenarios, diagrams, export, dashboard, serve"

framework-pdf:
	mkdir -p $(BUILD_DIR)
	pdflatex -output-directory=$(BUILD_DIR) $(TEX_FILE)
	pdflatex -output-directory=$(BUILD_DIR) $(TEX_FILE)
	find $(BUILD_DIR) -type f ! -name '*.pdf' ! -name '*.log' -delete

validate-model:
	cd village_tree && python validate_village_model.py && python check_needs_coverage.py

analyze-routes:
	cd village_tree && python analyze_dependency_routes.py

show-barriers:
	cd village_tree && python analyze_dependency_routes.py --barriers

rank-feasibility:
	cd village_tree && python analyze_dependency_routes.py --feasibility

run-scenarios:
	cd village_tree && python analyze_dependency_routes.py --scenarios

generate-diagrams:
	cd village_tree && python generate_governance_diagrams.py

export-public-data:
	cd village_tree && python export_public_data.py

build-dashboard: export-public-data

start-web-server: build-dashboard
	@echo "Serving dashboard at http://$(WEB_HOST):$(WEB_PORT)/"
	cd public && python3 -m http.server $(WEB_PORT) --bind $(WEB_HOST)

paper: framework-pdf

check: validate-model

analyze: analyze-routes

barriers: show-barriers

feasibility: rank-feasibility

scenarios: run-scenarios

diagrams: generate-diagrams

export: export-public-data

dashboard: build-dashboard

serve: start-web-server

clean:
	rm -rf $(BUILD_DIR)/
