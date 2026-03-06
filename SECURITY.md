# Security Policy

## Scope

This repository contains the Nebula bioinformatics pipeline — a DNA-only precision
wellness analysis system. Given the sensitivity of genetic data, we treat security
as a first-class concern.

## What this repository does NOT contain

- Real user VCF files or genetic data of any kind
- API keys, authentication tokens, or secrets
- Personally identifiable information
- Clinical or diagnostic data

All test data in `data/synthetic/` is computer-generated and contains no real
genetic information.

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Contact: security@nebula.bio

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested mitigations

You will receive acknowledgement within 48 hours and a full response within 7 days.

## Genetic data handling — developer responsibilities

If you are contributing to or deploying this codebase:

### Never commit real genetic data

The `.gitignore` blocks common genomic file formats (`.vcf`, `.bam`, `.fastq`, etc.).
If you need to test with real data locally:
- Store it outside the repository directory
- Pass it via CLI flags at runtime
- Delete it after testing

### Never log genotypes

The pipeline logs must not contain genotype data. If you add logging statements,
log rsIDs and rule IDs — never the actual genotype values (e.g. never log `"rs762551=AC"`).

### API keys

Set secrets as environment variables only:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
export NCBI_API_KEY=...
```

Never hardcode them. Never put them in config files that get committed.

### Dependency security

We pin dependencies in `pyproject.toml`. Before adding a new dependency:
- Check its maintenance status
- Check for known CVEs
- Prefer packages with minimal transitive dependencies

## GDPR and genetic data regulations

When deploying Nebula:
- Genetic data must be stored in the jurisdiction where the user resides
- Users must have the ability to request deletion of all their data
- Consent must be explicit and specific to genomic analysis
- Data retention policies must be defined before launch

This is not legal advice. Consult your legal team before deployment.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✓ Active  |
