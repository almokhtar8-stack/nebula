# Contributing to Nebula

Thank you for contributing. Because Nebula produces health-related outputs,
we hold contributions to a higher standard than a typical software project.
Please read this before opening a PR.

---

## Table of contents

- [Code of conduct](#code-of-conduct)
- [The most important rule](#the-most-important-rule)
- [Development setup](#development-setup)
- [Adding a new rule](#adding-a-new-rule)
- [Adding a whitelist variant](#adding-a-whitelist-variant)
- [Code contributions](#code-contributions)
- [Pull request checklist](#pull-request-checklist)

---

## Code of conduct

Be respectful. Health misinformation causes real harm — if a contribution
could mislead users about their health, it will not be merged regardless of
code quality.

---

## The most important rule

**No rule or whitelist variant enters the product without genetic counselor sign-off.**

This is non-negotiable. The sign-off must be documented in the PR description.
PRs that add or modify health-related content without documented clinical review
will be closed without merging.

---

## Development setup

```bash
# Clone
git clone https://github.com/your-org/nebula.git
cd nebula

# Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install in editable mode with dev extras
pip install -e ".[dev]"

# Run tests
make test

# Run the full pipeline against synthetic data
make run-synthetic

# Run surveillance dry-run
make surveillance-dry
```

---

## Adding a new rule

Rules live in `rulesets/v0_1.yml` (or the current version file). To add one:

### Step 1 — Evidence check

Before writing any code, verify the variant meets the evidence bar:
- ≥2 independent replication cohorts
- p < 5×10⁻⁸
- Reported in a peer-reviewed journal
- Effect size is clinically meaningful, not just statistically significant

Run the surveillance system first — if the variant is already in the queue
as a candidate, review that entry before creating a new one.

### Step 2 — Add the whitelist entry

In `data/whitelist/whitelist_v0_1.csv`, add a row:

```
rsid,gene,category,trait,risk_allele,ref_allele,evidence_grade,notes
rs000000,GENENAME,Nutrition,Trait name,A,G,Strong,Brief note
```

`evidence_grade` must be one of: `Strong`, `Moderate`, `Exploratory`

### Step 3 — Add the YAML rule

In `rulesets/v0_1.yml`, add a new entry following the existing structure exactly.
Copy an existing rule of the same category as a template. Key fields:

```yaml
- id: NUT-009                 # next sequential ID in category
  category: Nutrition
  description: "One sentence describing what this rule detects."
  trigger: nut_009            # must match the Python function name
  recommendation_text: >
    Write this as "Your genetics suggest..." not "You have..." or "You are..."
    Never use diagnostic language.
  reason: "One sentence explaining the science in plain English."
  evidence_grade: Strong      # must match whitelist entry
  base_confidence: 80         # 0-100, based on effect size and replication
  confidence_adjustments:
    - condition: relevant_questionnaire_field
      delta: 5
  practical_action: "Specific, actionable recommendation."
  review_interval: "6 months"
  disclaimer: "Standard disclaimer text."
  referral_trigger: false     # true only for Tier 3 pharmacogenomic findings
  output_tier: tier_1         # tier_1 | tier_2 | tier_3
```

### Step 4 — Add the Python trigger function

In `nebula/engine/evaluator.py`, add a decorated function:

```python
@_register("NUT-009")
def _nut_009(
    features: dict[str, GeneticFeature],
    prs: list[PRSScore],
    metadata: UserMetadata,
) -> bool:
    feat = features.get("rs000000")
    if not feat or not feat.found_in_vcf:
        return False
    return feat.risk_allele_count >= 1
```

The function name must match the `trigger` field in the YAML.

### Step 5 — Write a test

In `tests/test_engine.py`, add a test that verifies your rule fires correctly
for a sample with the triggering genotype.

### Step 6 — Document clinical sign-off

In your PR description, include:
- The PubMed IDs of the replication studies reviewed
- Name and credentials of the genetic counselor who reviewed the content
- The exact user-facing text they approved
- Any edge cases discussed (ancestry limitations, sex-specificity, etc.)

---

## Adding a whitelist variant

If you are adding a variant to the whitelist without creating a new rule
(e.g. a PRS sentinel variant or a surveillance-approved candidate):

1. Add to `data/whitelist/whitelist_v0_1.csv`
2. If updating an existing rule's confidence logic, update the YAML
3. Increment the minor version in the whitelist filename and `pyproject.toml`
   if the change is substantial
4. Document the evidence source and sign-off in the PR

---

## Code contributions

### Style

We follow PEP 8 with these additions:
- Type hints on all public functions
- Docstrings on all modules and public functions
- No line over 100 characters

```bash
make lint    # runs ruff + mypy
```

### No ML in the pipeline

The core analysis pipeline (`nebula/engine/`, `nebula/ingestion/`,
`nebula/report/`) must remain deterministic. No ML models, no LLM calls,
no probabilistic inference that cannot be fully explained to a non-technical
genetic counselor.

The surveillance summariser (`nebula/surveillance/summariser.py`) uses an
LLM for paper summarisation only — this is the single exception, and it
must not be expanded to influence report content.

### Adding a dependency

Before adding any `pip` dependency:
- Explain why it is necessary in the PR
- Check for CVEs
- Prefer stdlib alternatives if they exist
- Add it to `pyproject.toml` with a minimum version pin

---

## Pull request checklist

Before submitting:

- [ ] `make test` passes locally
- [ ] `make lint` passes
- [ ] I have not committed any VCF files, BAM files, or real genetic data
- [ ] I have not hardcoded any API keys or secrets
- [ ] If I added or modified a rule: genetic counselor sign-off is documented
- [ ] If I added a whitelist variant: evidence sources are cited (PMIDs)
- [ ] The recommendation text uses predisposition language, not diagnostic language
- [ ] I have added tests for any new logic
- [ ] I have updated the CHANGELOG

---

## Questions?

Open a GitHub Discussion (not an issue) for questions about evidence standards,
rule design, or the surveillance system.
