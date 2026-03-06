# Changelog

All notable changes to the Nebula pipeline are documented here.

Format: [Semantic Versioning](https://semver.org/)
Breaking changes are marked **[BREAKING]**.

---

## [Unreleased]

---

## [0.1.0] — 2026-03-06

### Initial MVP release

**Pipeline**
- VCF ingestion and QC (call rate ≥95%, het rate 20-35%, whitelist coverage check)
- 51-variant whitelist covering caffeine, lactose, folate, omega-3, iron, vitamin D,
  muscle fiber type, injury risk, chronotype, pharmacogenomics, HLA, and APOE
- 21 deterministic rules across Fitness, Nutrition, Recovery, and Health Risk categories
- Polygenic risk scores for CAD, T2D, breast cancer, and prostate cancer
  (synthetic weights — real GWAS weights to be substituted before beta launch)
- Three-tier safety classification (Tier 1: wellness, Tier 2: physician discussion,
  Tier 3: genetic counselor review)
- Structured JSON report (Sections A–J per Deliverable 4 spec)
- CLI: `nebula run`, `nebula validate-vcf`

**Literature surveillance system**
- PubMed E-utilities API client (free, no auth required)
- GWAS Catalog REST API client
- PGS Catalog API client for PRS model monitoring
- Deterministic evidence scorer (IF/THEN rules, no ML)
- Review queue with JSON persistence
- Optional Claude API paper summarisation (AI assists human reviewer only)
- CLI: `nebula surveillance run/review/approve/reject`
- Surveillance config: `rulesets/surveillance_config.yml`

**Developer tooling**
- pytest test suite (41 Python files, 5 test modules)
- GitHub Actions CI: lint → type check → tests → integration smoke test
- Makefile with common developer shortcuts
- Comprehensive `.gitignore` blocking genomic file formats and secrets
- `CONTRIBUTING.md` with evidence standards and genetic counselor sign-off requirements
- `SECURITY.md` with genetic data handling policy

**Synthetic test data**
- `sample_001.vcf`: Female, 34, vegetarian, endurance athlete, poor sleep
- `sample_001_meta.json`: Matching questionnaire
- `sample_002_meta.json`: Male, 28, omnivore, power athlete

### Known limitations

- PRS weights are synthetic — must be replaced with published GWAS weights before
  any real user data is processed
- Genome build liftover not yet implemented (GRCh38 VCFs may need preprocessing)
- Report is JSON only — PDF rendering to be added in Phase 2
- Surveillance AI summaries require manual ANTHROPIC_API_KEY configuration

---

## Version numbering

`MAJOR.MINOR.PATCH`

- MAJOR: Breaking changes to report schema or rule IDs
- MINOR: New rules, new whitelist variants, new features
- PATCH: Bug fixes, text corrections, threshold adjustments

Ruleset versions (`rulesets/v0_1.yml`) are versioned independently of the
pipeline code. A new ruleset version does not require a code release.
