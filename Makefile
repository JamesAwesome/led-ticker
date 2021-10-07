.PHONY: test

test:
	@echo "--- Running pytest ---"
	@docker-compose run --rm pytest
