# Nebula Makefile
# Common developer shortcuts. Run `make help` to see all commands.

.PHONY: help install test lint type-check run-synthetic surveillance-dry \
        surveillance-run review-queue clean fmt check-secrets

# ── Meta ──────────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "Nebula developer commands"
	@echo "─────────────────────────────────────────────────"
	@echo "  make install          Install package in editable mode"
	@echo "  make test             Run full test suite"
	@echo "  make lint             Lint + format check"
	@echo "  make type-check       Run mypy type checker"
	@echo "  make fmt              Auto-format code with ruff"
	@echo "  make check-secrets    Scan for accidental secrets in code"
	@echo ""
	@echo "  make run-synthetic    Run full pipeline on synthetic test data"
	@echo "  make validate-vcf     Validate the synthetic VCF only"
	@echo ""
	@echo "  make surveillance-dry  Surveillance dry-run (no network save)"
	@echo "  make surveillance-run  Real surveillance run (queries live APIs)"
	@echo "  make review-queue      Show current review queue"
	@echo ""
	@echo "  make clean            Remove generated files"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────────────────────

install:
	pip install -e ".[dev]"

# ── Quality ───────────────────────────────────────────────────────────────────

test:
	pytest tests/ -v --tb=short

test-fast:
	pytest tests/ -v --tb=short -x   # stop on first failure

lint:
	ruff check nebula/ tests/

fmt:
	ruff format nebula/ tests/

type-check:
	mypy nebula/ --ignore-missing-imports

check-secrets:
	@echo "Scanning for potential secrets..."
	@grep -rn "sk-ant-\|api_key\s*=\s*['\"][^'\"]\|password\s*=\s*['\"]" \
		nebula/ tests/ rulesets/ \
		--include="*.py" --include="*.yml" --include="*.yaml" \
		| grep -v "__pycache__" \
		| grep -v "test_" \
		| grep -v "# " \
		|| echo "No obvious secrets found."

# ── Pipeline ──────────────────────────────────────────────────────────────────

run-synthetic: out/
	nebula run \
		--vcf data/synthetic/sample_001.vcf \
		--meta data/synthetic/sample_001_meta.json \
		--whitelist data/whitelist/whitelist_v0_1.csv \
		--ruleset rulesets/v0_1.yml \
		--out out/

validate-vcf:
	nebula validate-vcf --vcf data/synthetic/sample_001.vcf

out/:
	mkdir -p out/

# ── Surveillance ──────────────────────────────────────────────────────────────

surveillance-dry: out/
	nebula surveillance run \
		--whitelist data/whitelist/whitelist_v0_1.csv \
		--config rulesets/surveillance_config.yml \
		--queue out/surveillance_queue.json \
		--dry-run

surveillance-run: out/
	@echo "This queries live PubMed and GWAS Catalog APIs."
	@echo "Rate limited — will take several minutes."
	nebula surveillance run \
		--whitelist data/whitelist/whitelist_v0_1.csv \
		--config rulesets/surveillance_config.yml \
		--queue out/surveillance_queue.json

surveillance-run-with-ai: out/
	@test -n "$$ANTHROPIC_API_KEY" || (echo "Error: ANTHROPIC_API_KEY not set" && exit 1)
	nebula surveillance run \
		--whitelist data/whitelist/whitelist_v0_1.csv \
		--config rulesets/surveillance_config.yml \
		--queue out/surveillance_queue.json \
		--ai-summaries

review-queue:
	nebula surveillance review \
		--queue out/surveillance_queue.json

review-strong:
	nebula surveillance review \
		--queue out/surveillance_queue.json \
		--signal strong_candidate

review-contradictions:
	nebula surveillance review \
		--queue out/surveillance_queue.json \
		--signal contradicts

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	rm -rf out/ build/ dist/ *.egg-info/ .pytest_cache/ .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "Cleaned. Note: out/surveillance_queue.json preserved if it exists."
