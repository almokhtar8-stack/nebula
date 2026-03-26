<div align="center">

<img src="assets/nebula-logo.png" alt="Nebula" height="120"/>

# NEBULA
### Precision Wellness Platform

**Every star leaves a fingerprint. So do you.**

[![Tests](https://img.shields.io/badge/tests-70%20passing-10B981?style=flat-square)](https://github.com/almokhtar8-stack/nebula/actions)
[![Python](https://img.shields.io/badge/python-3.12-3B82F6?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Pipeline](https://img.shields.io/badge/pipeline-v0.1.0-8B5CF6?style=flat-square)](https://github.com/almokhtar8-stack/nebula)
[![License](https://img.shields.io/badge/license-Proprietary-F59E0B?style=flat-square)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/almokhtar8-stack/nebula/ci.yml?branch=main&label=CI&style=flat-square)](https://github.com/almokhtar8-stack/nebula/actions)

[Live Platform](https://almokhtar8-stack.github.io/nebula/) · [Quickstart](#quickstart) · [File Guide](#what-every-file-does) · [Monday Scan](#how-the-automated-monday-scan-works) · [Roadmap](#roadmap)

</div>

---

## What Nebula Is

Nebula is a DNA-based precision wellness platform built for the MENA market. A user uploads their DNA file. Nebula reads 51 curated genetic markers, evaluates them through 21 science-backed rules, calculates inherited health risks across 4 conditions, and delivers a personalised wellness report — in plain language, not lab codes.

The platform is designed around a single principle: **every finding must be traceable to a published study, reviewed by a genetic counsellor, and explainable to a non-scientist**.

---

## The Big Picture

```
YOUR DNA FILE  +  YOUR LIFESTYLE ANSWERS
        │
        ▼
┌──────────────────────────────────────────────────────┐
│                   NEBULA PIPELINE                    │
│                                                      │
│  Step 1  Read your DNA file                         │
│  Step 2  Check quality — bad data never gets in     │
│  Step 3  Extract your 51 genetic markers            │
│  Step 4  Combine with your lifestyle answers        │
│  Step 5  Calculate health risk scores               │
│  Step 6  Run 21 rules → personalised insights       │
│  Step 7  Assemble your report                       │
└──────────────────────────────────────────────────────┘
        │                        │
        ▼                        ▼
  report.json               PDF report
  (structured data)         (what the client reads)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RUNNING IN THE BACKGROUND — EVERY MONDAY AT 2AM:

┌──────────────────────────────────────────────────────┐
│               SURVEILLANCE PIPELINE                  │
│                                                      │
│  Scans PubMed + GWAS Catalog for new discoveries    │
│  Scores by sample size, replication, effect size    │
│  Queues for genetic counsellor review               │
│  Approved findings enter the platform               │
│  Affected reports update automatically              │
└──────────────────────────────────────────────────────┘
```

---

## Numbers

| | |
|---|---|
| Genetic markers analysed | 51 curated variants |
| Wellness rules | 21 deterministic IF/THEN rules |
| Rule categories | Fitness (4), Nutrition (8), Sleep/Recovery (3), Health Risk (6) |
| Health risk models | 4 — Heart disease, Diabetes, Breast cancer, Prostate cancer |
| Automated tests | 70 passing |
| New discoveries queued | 145 awaiting counsellor review |
| Real DNA validated | HG00096 (1000 Genomes project, confirmed finding) |
| Pipeline latency | Under 1 second end-to-end |

---

## What Every File Does

This is the most important section. Every piece of the project explained in plain language.

---

### The Main Pipeline — `nebula/`

```
nebula/
│
├── cli.py
│   THE ENTRY POINT. All commands start here.
│   Run: nebula run, nebula validate-vcf, nebula surveillance
│   This is what the Makefile and CI both call.
│
├── engine/
│   │
│   ├── evaluator.py
│   │   RUNS THE 21 RULES. For each rule in the YAML, it calls
│   │   a matching Python trigger function. If the conditions are
│   │   met (right genotype + lifestyle context) → insight is added
│   │   to the report. All 21 trigger functions live here.
│   │
│   ├── prs.py
│   │   CALCULATES HEALTH RISK SCORES. Takes your genetic markers,
│   │   multiplies each by a published effect size weight, sums them
│   │   up, and converts to a percentile vs. a reference population.
│   │   Currently uses synthetic weights — real GWAS weights must be
│   │   substituted before beta launch.
│   │
│   └── rule_loader.py
│       READS AND VALIDATES THE YAML RULESET. Opens rulesets/v0_1.yml,
│       checks every rule has all required fields, raises an error if
│       anything is malformed. The pipeline cannot start with a broken
│       ruleset.
│
├── ingestion/
│   │
│   ├── vcf_reader.py
│   │   READS THE DNA FILE. Parses VCF format line by line. Handles:
│   │   missing calls, strand-flips (forward/reverse strand ambiguity),
│   │   quality filtering by GQ score, genome build detection (GRCh37
│   │   vs GRCh38), genotype encoding. Outputs raw RawVariant objects.
│   │
│   └── metadata_reader.py
│       READS THE QUESTIONNAIRE ANSWERS. Loads the JSON file from
│       scripts/questionnaire.py and validates every field using
│       Pydantic v2. If anything is out of range or wrong type,
│       it raises a clear error before the pipeline touches it.
│
├── report/
│   │
│   └── builder.py
│       ASSEMBLES THE FINAL REPORT. Takes all pipeline outputs and
│       builds one NebulaReport object: insights sorted by category,
│       watchlist (findings needing a doctor), next steps prioritised
│       by urgency, evidence table, QC summary, and fixed disclaimers.
│       Writes to out/report.json.
│
├── surveillance/
│   │
│   ├── runner.py
│   │   THE WEEKLY SCAN ORCHESTRATOR. Called by schedule_surveillance.py
│   │   every Monday. For each of the 51 rsIDs in the whitelist, it
│   │   calls PubMed + GWAS Catalog, scores the results, and saves
│   │   candidates to the review queue. Nothing enters the product
│   │   from here — this only populates the queue.
│   │
│   ├── scorer.py
│   │   SCORES NEW DISCOVERIES. For each candidate found by the scan,
│   │   it evaluates: sample size (n), replication count, effect size
│   │   (OR/beta), ancestry diversity. Returns one of:
│   │   strong_candidate / moderate_candidate / contradicts / weak.
│   │   Thresholds are set in surveillance_config.yml — no code change
│   │   needed to adjust them.
│   │
│   ├── queue.py
│   │   MANAGES THE REVIEW QUEUE FILE. Save, load, merge new candidates,
│   │   approve, reject. Handles atomic file writes (write to .tmp then
│   │   rename) so a crash never corrupts the queue.
│   │
│   ├── pubmed.py
│   │   PUBMED API CLIENT. Searches for papers mentioning each rsID
│   │   using NCBI E-utilities. Free public API, no key required for
│   │   basic use. Set NCBI_API_KEY in .env for higher rate limits.
│   │
│   ├── gwas_catalog.py
│   │   GWAS CATALOG API CLIENT. Fetches all genome-wide significant
│   │   associations for each rsID from the EBI GWAS Catalog REST API.
│   │   Free public API. Filters to p < 5×10⁻⁸ by default.
│   │
│   ├── pgs_catalog.py
│   │   PGS CATALOG CLIENT. Monitors for new or improved polygenic
│   │   score models for CAD, T2D, Breast Cancer, Prostate Cancer.
│   │   Runs monthly. When a better model is published, it flags it
│   │   for review so the PRS weights can be updated.
│   │
│   ├── summariser.py
│   │   OPTIONAL AI PAPER SUMMARIES. Uses Claude API to summarise
│   │   each paper in 3 structured sentences for the counsellor.
│   │   ONLY runs if ANTHROPIC_API_KEY is set in .env. ONLY used
│   │   to save the counsellor reading time — it never makes decisions.
│   │   The human approves or rejects every candidate.
│   │
│   └── models.py
│       DATA SHAPES FOR EVERYTHING SURVEILLANCE. Defines:
│       GWASHit, PubMedPaper, PGSModel, SurveillanceCandidate,
│       ReviewQueue, SurveillanceRun, EvidenceSignal, ReviewStatus.
│
├── whitelist/
│   │
│   └── extractor.py
│       WHITELIST LOADER + FEATURE EXTRACTION. Reads whitelist_v0_1.csv
│       and for each rsID, finds it in the user's VCF. Handles
│       strand-flips. If an rsID is absent from the VCF (common in
│       WGS data where only variant sites are recorded), it is treated
│       as homozygous reference — 0 copies of the risk allele.
│       Returns a GeneticFeature object per rsID.
│
├── schemas/
│   │
│   └── inputs.py
│       ALL DATA SHAPES FOR THE WHOLE PIPELINE. Every object that
│       moves between modules is defined here as a Pydantic v2 model:
│       RawVariant, SampleQCResult, UserMetadata, WhitelistEntry,
│       GeneticFeature, PRSScore, RuleResult, NebulaReport, and all
│       their enums. If you want to understand the data model,
│       start here.
│
└── utils/
    └── io.py
        WRITE JSON FILES. Creates parent directories if needed.
        That is all it does.
```

---

### The Rules — `rulesets/`

```
rulesets/
│
├── v0_1.yml
│   ALL 21 WELLNESS RULES. Plain YAML. A scientist with no Python
│   knowledge can read, understand, and edit this file.
│   Each rule contains:
│     id             — unique identifier (FIT-001, NUT-002, etc.)
│     trigger        — matches a Python function in evaluator.py
│     recommendation_text — what the user sees (plain English,
│                           no diagnostic language)
│     reason         — the science behind it (for clinicians)
│     evidence_grade — Strong / Moderate / Exploratory
│     base_confidence — 0–100 base score
│     confidence_adjustments — lifestyle context can raise/lower it
│     practical_action — what the user should actually do
│     output_tier    — tier_1 (user) / tier_2 (physician) /
│                      tier_3 (counsellor must review first)
│     referral_trigger — true/false
│
│   Adding a new rule = add YAML entry + register trigger function.
│   No other code changes needed.
│
└── surveillance_config.yml
    CONTROLS THE AUTOMATED WEEKLY SCAN. Adjust without code changes:
      schedule:
        pubmed_interval_days: 7      ← how often PubMed is scanned
        gwas_catalog_interval_days: 30
      thresholds:
        strong_candidate:
          min_sample_size: 50000     ← what counts as strong
          min_auto_score: 70
        contradiction:
          null_replication_keywords: [...] ← what triggers urgent review
      ai_summarisation:
        enabled: false               ← set true when API key is ready
      notifications:
        write_notification_file: true
        email.enabled: false         ← set true + configure SMTP
```

---

### The Whitelist — `data/whitelist/`

```
data/whitelist/
└── whitelist_v0_1.csv
    THE 51 GENETIC MARKERS NEBULA ANALYSES. Each row = one rsID.
    Columns: rsid, gene, category, trait, risk_allele, ref_allele,
             evidence_grade, notes

    Categories covered:
      Caffeine (3)     — CYP1A2, AHR, ADORA2A
      Alcohol (2)      — ALDH2, ADH1B
      Lactose (1)      — LCT
      B-Vitamins (3)   — MTHFR (x2), FUT2
      Vitamin D (4)    — VDR, CYP2R1, GC, DHCR7
      Nutrition (5)    — FTO, FADS1, HFE (x2), PPARG
      Cancer PRS (7)   — Breast cancer + Prostate cancer sentinels
      CAD PRS (4)      — Coronary artery disease sentinels
      T2D PRS (4)      — Type 2 diabetes sentinels
      Fitness (3)      — ACTN3, COL5A1, IL6
      Sleep (3)        — PER2, CLOCK, ADA
      Pharmacogenomics (9) — SLCO1B1, DPYD, CYP2C9/19, VKORC1
      Gastrointestinal (2) — HLA-DQ2.5, HLA-DQ8
      Cardiovascular (3)   — APOE (x2), IL10, CD95

    Nothing enters this file without:
      1. N > 10,000 in original study
      2. Replication in 2+ independent cohorts
      3. Genome-wide significance (p < 5×10⁻⁸)
      4. Genetic counsellor sign-off
```

---

### The Scripts — `scripts/`

These are the tools you run from the command line.

```
scripts/
│
├── questionnaire.py
│   STEP 1 (for real users). Interactive terminal questionnaire.
│   Guides through 6 sections: basic profile, fitness, nutrition,
│   sleep, medical history, family history. Saves a validated JSON
│   file to data/meta/SAMPLE_meta.json.
│   Run: python scripts/questionnaire.py --sample-id MY_SAMPLE
│   Or edit existing: python scripts/questionnaire.py --edit data/meta/MY_SAMPLE_meta.json
│
├── download_sample.py
│   STEP 2 (for testing with real DNA). Downloads a real 1000 Genomes
│   VCF using bcftools HTTP streaming. Only fetches the 51 positions
│   Nebula needs — no 50GB download. Maps exact GRCh38 coordinates
│   for all 51 rsIDs. Injects rsIDs into blank VCF ID fields.
│   Run: python scripts/download_sample.py --sample HG00096
│   List samples: python scripts/download_sample.py --list-samples
│
├── render_report.py
│   STEP 3 (after the pipeline). Converts out/report.json into a
│   branded PDF using ReportLab. Produces:
│     - Cover page: logo, summary stats, animated PRS population bars
│     - Insights by category (expandable cards with evidence grade)
│     - Watchlist section (Tier 2 + Tier 3 findings)
│     - Next steps prioritised by urgency (urgent/recommended/routine)
│     - Evidence table (rule ID → grade → confidence → sources)
│     - Disclaimers
│   Run: python scripts/render_report.py --report out/report.json --out out/report.pdf
│
├── review_queue.py
│   FOR THE GENETIC COUNSELLOR — CLI VERSION. Reviews surveillance
│   candidates one by one. When you ACCEPT a candidate it:
│     1. Adds the rsID to whitelist_v0_1.csv
│     2. Writes a rule stub to rulesets/pending_rules.yml
│     3. Marks the candidate as APPROVED in the queue
│     4. Logs the decision with timestamp to data/review_log.jsonl
│   When you REJECT it never resurfaces.
│   Run: python scripts/review_queue.py --interactive
│   List: python scripts/review_queue.py --list
│   Stats: python scripts/review_queue.py --stats
│
├── review_dashboard.html
│   FOR THE GENETIC COUNSELLOR — BROWSER VERSION. Open in any
│   browser. Drag in out/surveillance_queue.json. Shows all
│   candidates with signal type, evidence, paper links, AI summary.
│   Contradictions shown in red with urgent banner.
│   Approve/Reject buttons generate the CLI command to copy/run.
│   Open: open scripts/review_dashboard.html
│   No server needed. Runs entirely in the browser.
│
├── fetch_candidates.py
│   MANUAL SURVEILLANCE RUN. Queries GWAS Catalog + ClinVar +
│   PGS Catalog across all trait categories. Scores and saves to
│   queue. Use this for one-off scans or to test the system.
│   Run: python scripts/fetch_candidates.py --dry-run
│   Run: python scripts/fetch_candidates.py --sources gwas clinvar
│   Run: python scripts/fetch_candidates.py --category Fitness
│
├── schedule_surveillance.py
│   WHAT RUNS EVERY MONDAY AUTOMATICALLY (via cron). Checks if
│   a scan is due. If yes, runs the full surveillance pipeline,
│   saves the queue, writes out/surveillance_notification.txt,
│   and optionally sends an email. Set up with cron — see below.
│
├── notify.py
│   SENDS EMAIL NOTIFICATIONS via Brevo API. Called by the scheduler
│   when surveillance finds something important.
│   Needs BREVO_API_KEY in .env.
│
└── nebula_dashboard.jsx
    REACT REPORT VIEWER. An interactive browser-based report
    viewer. Reads report.json data. Tabs for each category,
    expandable insight cards, animated PRS bars, next steps list.
    For the client portal (v0.2.0).
```

---

### The Tests — `tests/`

```
tests/
│
├── conftest.py
│   SHARED TEST FIXTURES. Defines paths to synthetic VCF, metadata,
│   whitelist, and ruleset so every test module can use them.
│
├── test_ingestion.py  (17 tests)
│   Tests VCF parsing edge cases: missing calls, bad filters, genome
│   build detection, sample ID extraction, malformed lines. Tests
│   metadata loading: bad JSON, out-of-range age, missing fields.
│   Also tests QC thresholds: low call rate fails, whitelist coverage.
│
├── test_whitelist.py  (10 tests)
│   Tests whitelist CSV loading: missing columns raises error, wrong
│   file raises FileNotFoundError. Tests feature extraction: CYP1A2
│   heterozygous → 1 risk allele, LCT homozygous → 2 risk alleles.
│   Tests strand-flip correction. Tests absent rsIDs → hom ref.
│
├── test_engine.py  (23 tests)
│   Tests rule evaluation: verifies NUT-001 (caffeine), NUT-002
│   (lactose), REC-003 (caffeine+sleep) fire for SAMPLE_001.
│   Tests confidence bounds (0–100). Tests Tier 3 classification
│   for RISK-005 (DPYD). Tests PRS computation returns correct
│   conditions for male/female.
│
├── test_report.py  (12 tests)
│   Tests report structure: all sections present, sample_id
│   propagated, report_id is valid UUID, summary counts consistent.
│   Tests watchlist only contains Tier 2/3. Tests no diagnostic
│   language ("you have", "you are diagnosed"). Tests JSON serialisation.
│
└── test_surveillance.py  (18 tests)
    ALL NETWORK CALLS ARE MOCKED — runs fully offline.
    Tests scorer: strong signal for large n, weak for small n,
    contradiction detection from paper titles, multi-ancestry bonus.
    Tests queue: save/load roundtrip, merge logic, approve/reject,
    contradiction always re-opens even if previously reviewed.
    Tests runner: dry run does not write file, real run saves queue.
```

---

## Quickstart

### Requirements

```bash
pip install -e ".[dev]"
# Also required for download_sample.py:
conda install -c bioconda bcftools
# Also required for render_report.py:
pip install reportlab
```

### Full pipeline in 4 commands

```bash
# 1. Answer the lifestyle questionnaire (saves to data/meta/)
python scripts/questionnaire.py --sample-id SAMPLE_001

# 2. Download a real DNA sample for testing (uses bcftools, ~200KB)
python scripts/download_sample.py --sample HG00096

# 3. Run the full pipeline
nebula run \
  --vcf data/vcf/HG00096.vcf \
  --meta data/meta/SAMPLE_001_meta.json \
  --out out/

# 4. Generate the PDF report
python scripts/render_report.py \
  --report out/report.json \
  --out out/nebula_report.pdf
```

### Or use Make

```bash
make install          # install dependencies
make run-synthetic    # run pipeline on synthetic test data
make test             # run 70 tests
make lint             # ruff + mypy
make surveillance-dry # see what surveillance would find (no save)
make review-queue     # show current review queue
```

### Run the tests

```bash
pytest tests/ -v
# 70 passing
```

---

## How the Automated Monday Scan Works

This is the surveillance system. It keeps Nebula's science current without any manual work.

### Set it up once with cron

```bash
# Open crontab
crontab -e

# Add this line — runs every Monday at 2am
0 2 * * 1 cd /path/to/nebula && python scripts/schedule_surveillance.py >> out/surveillance.log 2>&1
```

### What happens every Monday at 2am

```
schedule_surveillance.py
        │
        ├─ Checks: is PubMed scan due? (every 7 days)
        ├─ Checks: is GWAS scan due? (every 30 days)
        │
        └─ Calls runner.py → for each of 51 rsIDs:
                │
                ├─ PubMed: search for new papers mentioning this rsID
                ├─ GWAS Catalog: fetch new genome-wide associations
                │
                └─ scorer.py evaluates each finding:
                        n >= 50,000 + replicated + strong effect
                        → signal: strong_candidate  (counsellor review)
                        n >= 10,000 + replicated
                        → signal: moderate_candidate (watch list)
                        null result found in existing whitelist entry
                        → signal: contradicts  (URGENT)
                        below thresholds
                        → signal: weak  (logged, not queued)
        │
        ├─ Saves results to out/surveillance_queue.json
        ├─ Writes out/surveillance_notification.txt
        └─ Sends email if NEBULA_NOTIFY_EMAIL is set
```

### What you do after the scan

```bash
# See what was found
python scripts/review_queue.py --list

# See only the urgent ones
python scripts/review_queue.py --list --signal contradicts

# Or open the browser dashboard (drag in the queue JSON)
open scripts/review_dashboard.html

# Review candidates one by one in the terminal
python scripts/review_queue.py --interactive --reviewer "Dr. Smith"

# Accept a specific finding
python scripts/review_queue.py --accept surv_rs762551_abc01 --reviewer "Dr. Smith"

# Reject a finding
python scripts/review_queue.py --reject surv_rs762551_abc01 --reason "small sample, single cohort"
```

### What happens when you accept a candidate

```
python scripts/review_queue.py --accept <candidate_id>
        │
        ├─ 1. Adds rsID to data/whitelist/whitelist_v0_1.csv
        ├─ 2. Writes a rule stub to rulesets/pending_rules.yml
        │       (counsellor fills in the recommendation text, evidence)
        ├─ 3. Marks candidate as APPROVED in the queue
        └─ 4. Logs decision with timestamp + reviewer name

Next step:
  Open rulesets/pending_rules.yml
  Fill in: recommendation_text, practical_action, evidence_grade,
           confidence, disclaimer, output_tier
  Move the completed rule to rulesets/v0_1.yml
  Increment the version field in v0_1.yml
  Run: make test  (ensure nothing broke)
  Commit and push
```

---

## How the PDF Report Works

```
nebula run ...
    └─ writes out/report.json

python scripts/render_report.py --report out/report.json --out out/report.pdf
    └─ reads report.json
    └─ builds branded PDF with ReportLab:

        Page 1: Cover
          ├─ Logo + "Your Genetic Wellness Report"
          ├─ Sample ID, date, pipeline version
          ├─ 4 stat boxes: total insights, strong evidence, moderate, physician flags
          ├─ Top 3 highlight insights
          └─ PRS population bars (gradient: green → red, marker at your percentile)

        Pages 2+: Insights by category
          Each insight card shows:
          ├─ Rule ID + category + evidence grade (colour coded)
          ├─ Confidence bar (IIIIIIIII. 90%)
          ├─ Recommendation text (plain English)
          ├─ "What to do" box (cyan background)
          ├─ Data sources
          └─ Disclaimer

        Watchlist section
          Tier 2 findings: amber header, "physician discussion recommended"
          Tier 3 findings: red header, "genetic counsellor review required"

        Next steps
          Numbered, colour-coded by urgency:
          Red = urgent, Amber = recommended, Green = routine

        Evidence table
          Rule → Evidence grade → Confidence → Data sources

        Disclaimers
          7 fixed legal/safety statements
```

---

## The Three-Tier Safety System

Every finding is automatically routed based on its clinical weight. Nothing is manual.

| Tier | Finding type | Who sees it | Example |
|---|---|---|---|
| **Tier 1** | Wellness insight | Delivered to user directly | "You digest caffeine slowly" |
| **Tier 2** | Health risk flag | User sees it + physician discussion recommended | "Elevated heart disease tendency" |
| **Tier 3** | Clinical finding | HELD until a genetic counsellor reviews and approves | DPYD chemotherapy toxicity risk |

No Tier 3 finding ever reaches a user automatically. The user sees: *"One finding requires specialist review before we can share it."*

This logic lives in `rulesets/v0_1.yml` under `output_tier`. No code change needed to change a finding's tier.

---

## Environment Variables

Create a `.env` file in the project root (never commit it):

```bash
# Optional — enables AI paper summaries in surveillance
ANTHROPIC_API_KEY=sk-ant-...

# Optional — higher PubMed rate limits (free at ncbi.nlm.nih.gov/account)
NCBI_API_KEY=your_key_here

# Optional — email for surveillance notifications
NEBULA_NOTIFY_EMAIL=you@example.com

# Optional — Brevo SMTP for email (used by notify.py)
BREVO_API_KEY=your_key_here
```

---

## Full Project Structure

```
nebula/
│
├── nebula/                         Core Python package
│   ├── cli.py                      Entry point — all CLI commands
│   ├── engine/
│   │   ├── evaluator.py            21 deterministic rule triggers
│   │   ├── prs.py                  Polygenic risk score computation
│   │   └── rule_loader.py          YAML ruleset loader + validator
│   ├── ingestion/
│   │   ├── vcf_reader.py           VCF parsing + QC
│   │   └── metadata_reader.py      Questionnaire JSON loader
│   ├── report/
│   │   └── builder.py              Report assembly (Sections A–J)
│   ├── schemas/
│   │   └── inputs.py               All Pydantic v2 data models
│   ├── surveillance/
│   │   ├── runner.py               Weekly scan orchestrator
│   │   ├── scorer.py               Evidence scoring (IF/THEN, no ML)
│   │   ├── queue.py                Queue persistence + merge logic
│   │   ├── pubmed.py               PubMed E-utilities API client
│   │   ├── gwas_catalog.py         GWAS Catalog REST API client
│   │   ├── pgs_catalog.py          PGS Catalog API client
│   │   ├── summariser.py           Claude API paper summaries (optional)
│   │   └── models.py               Surveillance data models
│   ├── whitelist/
│   │   └── extractor.py            Whitelist loader + feature extraction
│   └── utils/
│       └── io.py                   JSON file writer
│
├── rulesets/
│   ├── v0_1.yml                    21 wellness rules (edit here, no Python)
│   └── surveillance_config.yml     Scan schedule + thresholds
│
├── data/
│   ├── whitelist/
│   │   └── whitelist_v0_1.csv      51 curated genetic markers
│   └── synthetic/                  Synthetic test data (tracked in git)
│       ├── sample_001.vcf          Female, 34, vegetarian, poor sleep
│       ├── sample_001_meta.json    Matching questionnaire
│       └── sample_002_meta.json    Male, 28, omnivore, power athlete
│
├── scripts/
│   ├── questionnaire.py            Step 1: collect lifestyle answers
│   ├── download_sample.py          Step 2: get test VCF from 1000 Genomes
│   ├── render_report.py            Step 3: generate branded PDF
│   ├── review_queue.py             Counsellor: CLI queue review tool
│   ├── review_dashboard.html       Counsellor: browser queue review tool
│   ├── fetch_candidates.py         Manual surveillance run
│   ├── schedule_surveillance.py    Automated Monday cron scheduler
│   ├── notify.py                   Email notifications via Brevo
│   └── nebula_dashboard.jsx        React report viewer (client portal v0.2)
│
├── tests/
│   ├── conftest.py                 Shared fixtures
│   ├── test_ingestion.py           VCF + metadata tests (17)
│   ├── test_engine.py              Rule engine + PRS tests (23)
│   ├── test_report.py              Report builder tests (12)
│   ├── test_surveillance.py        Surveillance tests, mocked (18)
│   └── test_whitelist.py           Whitelist tests (10)
│
├── .github/
│   ├── workflows/ci.yml            GitHub Actions: lint → types → tests → smoke
│   ├── pull_request_template.md    PR checklist with clinical sign-off
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.yml          Structured bug report with data safety check
│       ├── new_rule.yml            New rule proposal with evidence standards
│       └── surveillance_candidate.yml  Counsellor review tracking
│
├── out/                            Pipeline output (gitignored)
├── index.html                      Landing page (GitHub Pages)
├── pyproject.toml                  Python package config
├── Makefile                        Developer shortcuts
├── CHANGELOG.md                    Version history
├── CONTRIBUTING.md                 Evidence standards + PR guide
├── SECURITY.md                     Genetic data handling policy
├── LICENSE                         Proprietary license
├── .gitignore                      Blocks VCF, BAM, FASTQ, secrets
└── .env.example                    Template for environment variables
```

---

## Roadmap

### v0.1.0 — MVP (complete)
- [x] Full 7-stage pipeline: VCF → QC → features → questionnaire → PRS → rules → report
- [x] 51 genetic markers, 21 rules, 4 PRS models
- [x] Three-tier safety routing
- [x] PDF report renderer with population bars
- [x] Interactive questionnaire CLI
- [x] Weekly surveillance pipeline (PubMed + GWAS Catalog + PGS Catalog)
- [x] Counsellor review tools: CLI + browser dashboard
- [x] 70 automated tests, GitHub Actions CI
- [x] Landing page (GitHub Pages)

### v0.2.0 — Client Portal
- [ ] React web portal for end users
- [ ] User authentication
- [ ] Interactive report viewer (no PDF required)
- [ ] Admin dashboard

### v0.3.0 — Clinical
- [ ] Genetic counsellor review portal
- [ ] Physician referral workflow
- [ ] HL7 FHIR report export
- [ ] Arabic language support

### v1.0.0 — Commercial Launch
- [ ] Payment and kit fulfilment pipeline
- [ ] Saudi regulatory pathway (Saudi FDA)
- [ ] Replace synthetic PRS weights with published GWAS weights (PGS000013 for CAD, PGS000015 for BrCa)
- [ ] Ancestry-specific calibration for MENA population

---

## Vision 2030 Alignment

Nebula is designed from the ground up for the Saudi market, directly aligned with Vision 2030 health objectives:

- **Preventive healthcare shift** — from treatment to early genetic insight
- **Digital health infrastructure** — cloud-ready, API-first, deployable on Saudi infrastructure
- **Health data sovereignty** — all data can remain within Saudi jurisdiction
- **Human capital development** — personalised health optimisation tools for citizens
- **MENA-first design** — Arabic language and MENA ancestry data in roadmap

---

## Important Limitations (known before beta launch)

| Limitation | Impact | Fix |
|---|---|---|
| PRS weights are synthetic | Risk scores are directionally correct but not clinically calibrated | Replace with PGS000013 (CAD), PGS000015 (BrCa) etc. before beta |
| No genome build liftover | GRCh38 VCFs may need preprocessing | Implement liftover in vcf_reader.py |
| European reference population | PRS less accurate for other ancestries | Add MENA reference panel |
| No real user auth | Cannot be deployed to real users | v0.2.0 adds authentication |

---

## Intellectual Property

This repository is proprietary. The pipeline architecture, rule engine, three-tier safety system, and surveillance framework are the intellectual property of Almokhtar Aljarodi.

Viewing and evaluation permitted. Commercial use, reproduction, or redistribution prohibited without written permission.

Patent application in preparation — Saudi Authority for Intellectual Property (SAIP).

See [LICENSE](LICENSE) for full terms.

---

## Contact

**Almokhtar Aljarodi**
Founder, Nebula Precision Wellness

[GitHub](https://github.com/almokhtar8-stack) · [Platform](https://almokhtar8-stack.github.io/nebula/)

---

<div align="center">
<br/>
<em>Every star leaves a fingerprint. So do you.</em>
<br/><br/>
<strong>NEBULA · TRANSFORMING LIVES THROUGH WELLNESS</strong>
</div>
