GO ?= go
PYTHON ?= python
TEST_ARGS ?=
FUZZ_TIME ?= 1000x
FUZZ_PARALLEL ?= 2

.DEFAULT_GOAL := help
.PHONY: help build test test-race tools fmt fmt-check imports-check fix fix-check vet staticcheck lint errcheck security security-smoke lint-smoke errcheck-smoke imports-smoke fix-gate-test coverage coverage-check coverage-smoke govulncheck fuzz deps tidy check ci

help:
	@echo make tools - Install pinned analysis tools into ignored .tools/ci-bin
	@echo make build / test / test-race - Build and test all packages
	@echo make check - Run formatting, analysis debt gates, and native coverage
	@echo make ci - Run all local quality gates, tool fixtures, race, and fuzz
	@echo make fmt / fmt-check - Apply or check imports/formatting, preserving CRLF
	@echo make fix / fix-check - Apply or check Go modernization
	@echo make vet / staticcheck / lint / errcheck / security / govulncheck
	@echo make coverage-check / coverage-smoke - Native package coverage and gate tests
	@echo make fuzz - Bounded parser exploration, FUZZ_TIME defaults to 1000x
	@echo Baseline findings remain visible; new findings and stale entries fail.

tools:
	$(PYTHON) scripts/ci.py install
build:
	$(GO) build ./...
	$(GO) build -o .tools/bin/ ./cmd/dzdeploy
test:
	$(GO) test -count=1 $(TEST_ARGS) ./...
test-race:
	$(GO) test -race -count=1 $(TEST_ARGS) ./...
fmt:
	$(PYTHON) scripts/ci.py format --write
fmt-check imports-check:
	$(PYTHON) scripts/ci.py format
fix:
	$(GO) fix ./...
fix-check:
	$(PYTHON) scripts/ci.py fix
vet:
	$(GO) vet ./...
staticcheck:
	$(PYTHON) scripts/ci.py staticcheck
lint:
	$(PYTHON) scripts/ci.py revive
errcheck:
	$(PYTHON) scripts/ci.py errcheck
security:
	$(PYTHON) scripts/ci.py gosec
security-smoke lint-smoke errcheck-smoke imports-smoke fix-gate-test:
	$(PYTHON) scripts/smoke_ci.py
coverage coverage-check:
	$(PYTHON) scripts/ci.py coverage
coverage-smoke:
	$(PYTHON) -m unittest discover -s scripts -p "test_*.py"
govulncheck:
	$(PYTHON) scripts/ci.py vulnerabilities
fuzz:
	$(GO) test ./internal/deploy -run "^$$" -fuzz "^FuzzSafeRelative$$" -fuzztime $(FUZZ_TIME) -fuzzminimizetime 2s -parallel $(FUZZ_PARALLEL) -timeout 2m
	$(GO) test ./internal/logreader -run "^$$" -fuzz "^FuzzDecodeRecord$$" -fuzztime $(FUZZ_TIME) -fuzzminimizetime 2s -parallel $(FUZZ_PARALLEL) -timeout 2m
deps:
	$(GO) mod download
tidy:
	$(GO) mod tidy
check:
	$(PYTHON) scripts/ci.py all
ci: tools
	$(MAKE) coverage-smoke
	$(PYTHON) scripts/smoke_ci.py
	$(MAKE) check vet build test-race govulncheck fuzz
	$(GO) mod verify
	$(PYTHON) scripts/ci.py tidy
	git diff --exit-code
