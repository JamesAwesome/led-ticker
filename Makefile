.PHONY: build-test test


build-test:
	@echo "--- building test image ---"
	@docker-compose -f docker-compose.ci.yml build pytest


test:
	@echo "--- Running pytest ---"
	@docker-compose run --rm pytest


shell:
	@echo "--- Running dev shell ---"
	@docker-compose run --rm pytest /bin/bash -l
