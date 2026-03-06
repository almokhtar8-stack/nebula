# Nebula — DNA-Only Precision Wellness Backend MVP

> **Synthetic data only. No real genetic data. Not for clinical use.**

## What This Is

Backend pipeline for the Nebula precision wellness MVP. Takes a VCF and a
structured questionnaire, runs QC, extracts whitelisted variants, computes PRS
scores, evaluates 21 deterministic rules, and produces a structured `report.json`.

---

## Quick Start

### 1. Install

```bash
# Clone the repo
git clone <repo> && cd nebula

# Create a virtual environment (recommended)
python -m venv .venv && source .venv/bin/activate

# Install (with dev dependencies)
pip install -e ".[dev]"
```

### 2. Run the full pipeline

```bash
nebula run \
  --vcf data/synthetic/sample_001.vcf \
  --meta data/synthetic/sample_001_meta.json \
  --whitelist data/whitelist/whitelist_v0_1.csv \
  --ruleset rulesets/v0_1.yml \
  --out out/
```

Output: `out/report.json`

### 3. Run tests

```bash
pytest
```

### 4. Lint

```bash
ruff check nebula/ tests/
ruff format nebula/ tests/
```

---

## CLI Reference

```
nebula run [OPTIONS]

  Options:
    --vcf PATH           Input VCF file [required]
    --meta PATH          Metadata/questionnaire JSON [required]
    --whitelist PATH     Variant whitelist CSV [default: data/whitelist/whitelist_v0_1.csv]
    --ruleset PATH       YAML ruleset [default: rulesets/v0_1.yml]
    --out PATH           Output directory [default: out/]
    --fail-on-qc         Exit non-zero if QC errors present
    --debug              Enable debug logging

nebula validate-vcf --vcf PATH
  Validate a VCF and print QC summary. Exit 0 = pass, 1 = fail.
```

---

## Project Structure

```
nebula/
├── nebula/
│   ├── cli.py                    # Click CLI entry point
│   ├── schemas/
│   │   └── inputs.py             # All Pydantic internal schemas
│   ├── ingestion/
│   │   ├── vcf_reader.py         # VCF parser + QC
│   │   └── metadata_reader.py    # Questionnaire JSON loader
│   ├── whitelist/
│   │   └── extractor.py          # Whitelist loader + feature extraction
│   ├── engine/
│   │   ├── rule_loader.py        # YAML ruleset loader + validation
│   │   ├── evaluator.py          # Deterministic rule evaluation
│   │   └── prs.py                # PRS computation (synthetic weights)
│   ├── report/
│   │   └── builder.py            # Report assembler (Sections A–J)
│   └── utils/
│       └── io.py                 # JSON output helper
├── rulesets/
│   └── v0_1.yml                  # ALL 21 rules — the only place rule logic lives
├── data/
│   ├── whitelist/
│   │   └── whitelist_v0_1.csv    # Curated variant whitelist (51 entries)
│   └── synthetic/
│       ├── sample_001.vcf        # Synthetic test VCF (female, endurance athlete)
│       ├── sample_001_meta.json  # Synthetic questionnaire
│       └── sample_002_meta.json  # Second synthetic user (male, power athlete)
├── tests/
│   ├── conftest.py
│   ├── test_ingestion.py
│   ├── test_whitelist.py
│   ├── test_engine.py
│   └── test_report.py
├── .github/
│   └── workflows/
│       └── ci.yml
└── pyproject.toml
```

---


---

## Literature Surveillance System

The surveillance system monitors PubMed and GWAS Catalog for new evidence on every variant in your whitelist. Runs on a schedule, scores findings automatically, places candidates in a review queue. **Nothing enters the product without human approval.**

### Run surveillance

```bash
# Dry run — see what would be found without saving
nebula surveillance run --dry-run

# Real run — save to queue
nebula surveillance run --since 2025/01/01

# With AI summaries (requires ANTHROPIC_API_KEY)
nebula surveillance run --ai-summaries

# Review pending candidates
nebula surveillance review
nebula surveillance review --signal strong_candidate
nebula surveillance review --signal contradicts

# Approve or reject
nebula surveillance approve --id <candidate_id> --reviewer "Dr Smith"
nebula surveillance reject  --id <candidate_id> --reviewer "Dr Smith" --notes "weak evidence"
```

### Signal types

| Signal | Meaning | Action needed |
|--------|---------|---------------|
| `strong_candidate` | All evidence thresholds met | Genetic counselor review |
| `moderate_candidate` | Partial evidence | Watch list |
| `contradicts` | Conflicts with existing entry | **Urgent — review immediately** |
| `weak` | Below thresholds | Logged only, not queued |

Thresholds live in `rulesets/surveillance_config.yml`.

---

## Pipeline Flow

```
VCF ──────────────────┐
                       ├─→ parse_vcf() → run_qc()
Questionnaire JSON ───┘                     │
                                            ▼
                                   load_whitelist()
                                   extract_features()
                                            │
                                            ▼
                                   compute_prs()
                                   evaluate_rules()   ← rulesets/v0_1.yml
                                            │
                                            ▼
                                   build_report()
                                            │
                                            ▼
                                   out/report.json
```

---

## Report JSON Structure

```json
{
  "schema_version": "1.0",
  "report_id": "<uuid>",
  "sample_id": "SAMPLE_001",
  "generated_at": "<ISO 8601>",
  "pipeline_version": "0.1.0",
  "ruleset_version": "0.1.0",
  "summary": { ... },           // Section A: top insights, counts
  "insights": {                 // Sections C-G by category
    "Fitness": [...],
    "Nutrition": [...],
    "Recovery/Sleep": [...],
    "Health Risk": [...]
  },
  "watchlist": [...],           // Section F: Tier 2 + Tier 3 items
  "evidence_confidence": [...], // Section H: evidence table
  "next_steps": [...],          // Section I: follow-up actions
  "disclaimers": [...],         // Section J: fixed legal/safety text
  "qc_summary": { ... },        // QC metadata
  "prs_scores": [...]           // PRS raw scores + percentiles
}
```

---

## Adding or Modifying Rules

Rules live **entirely** in `rulesets/v0_1.yml`. To add a rule:

1. Add an entry in the YAML with a new `id` (e.g. `NUT-009`).
2. Register a trigger function in `nebula/engine/evaluator.py` with `@_register("NUT-009")`.
3. Increment `version` in the YAML.
4. Write a test in `tests/test_engine.py`.

No other files need to change.

---

## Hard Constraints (enforced)

- DNA-only. No RNA, wearables, or clinical labs.
- No ML models. No LLM calls. All logic is deterministic IF/THEN.
- No real genetic data. Synthetic data only in this repo.
- No external network calls. Runs fully offline.
- Rules live outside code in versioned YAML.
- No diagnostic language in recommendation text.
- Tier 3 findings flagged for human review before report release.
