"""
nebula.whitelist.extractor — Load the variant whitelist and resolve it
against a user's parsed VCF variants.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from nebula.schemas import (
    EvidenceGrade,
    GeneticFeature,
    RawVariant,
    WhitelistEntry,
)

logger = logging.getLogger(__name__)


class WhitelistLoadError(ValueError):
    pass


def _parse_evidence_grade(raw: str) -> EvidenceGrade:
    mapping = {
        "strong": EvidenceGrade.STRONG,
        "moderate": EvidenceGrade.MODERATE,
        "weak_moderate": EvidenceGrade.MODERATE,
        "exploratory": EvidenceGrade.EXPLORATORY,
        "weak": EvidenceGrade.EXPLORATORY,
    }
    return mapping.get(raw.lower().strip(), EvidenceGrade.EXPLORATORY)


def load_whitelist(whitelist_path: Path) -> list[WhitelistEntry]:
    """
    Load the variant whitelist CSV.
    Returns a list of WhitelistEntry objects.
    """
    whitelist_path = Path(whitelist_path)
    if not whitelist_path.exists():
        raise FileNotFoundError(f"Whitelist not found: {whitelist_path}")

    required_cols = {"rsid", "gene", "trait", "category", "evidence_grade"}
    entries: list[WhitelistEntry] = []

    with open(whitelist_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise WhitelistLoadError("Whitelist CSV is empty or has no header row.")

        col_set = {c.strip().lower() for c in reader.fieldnames}
        missing_cols = required_cols - col_set
        if missing_cols:
            raise WhitelistLoadError(
                f"Whitelist CSV is missing required columns: {missing_cols}"
            )

        for row in reader:
            row = {k.strip().lower(): v.strip() for k, v in row.items()}
            rsid = row.get("rsid", "")
            if not rsid:
                continue
            entries.append(
                WhitelistEntry(
                    rsid=rsid,
                    gene=row.get("gene", ""),
                    category=row.get("category", ""),
                    trait=row.get("trait", ""),
                    risk_allele=row.get("risk_allele", ""),
                    ref_allele=row.get("ref_allele", ""),
                    evidence_grade=_parse_evidence_grade(row.get("evidence_grade", "")),
                    notes=row.get("notes", ""),
                )
            )

    if not entries:
        raise WhitelistLoadError("Whitelist CSV contains no entries.")

    logger.info("Loaded %d whitelist entries from %s", len(entries), whitelist_path)
    return entries


def whitelist_rsids(entries: list[WhitelistEntry]) -> set[str]:
    """Return the set of rsIDs from a loaded whitelist."""
    return {e.rsid for e in entries}


def extract_features(
    whitelist: list[WhitelistEntry],
    variants: list[RawVariant],
) -> list[GeneticFeature]:
    """
    Match VCF variants to whitelist entries and resolve genotypes.
    Returns a list of GeneticFeature objects (one per whitelist entry).
    """
    vcf_by_rsid: dict[str, RawVariant] = {
        v.rsid: v for v in variants if v.rsid and v.genotype != "missing"
    }

    features: list[GeneticFeature] = []

    for entry in whitelist:
        vcf_var = vcf_by_rsid.get(entry.rsid)

        if vcf_var is None or not vcf_var.filter_pass:
            features.append(
                GeneticFeature(
                    rsid=entry.rsid,
                    gene=entry.gene,
                    category=entry.category,
                    trait=entry.trait,
                    genotype="",
                    alleles=[],
                    risk_allele=entry.risk_allele,
                    risk_allele_count=0,
                    evidence_grade=entry.evidence_grade,
                    found_in_vcf=False,
                )
            )
            continue

        risk_allele_count = sum(
            1 for allele in vcf_var.gt_alleles
            if allele == entry.risk_allele
        )

        features.append(
            GeneticFeature(
                rsid=entry.rsid,
                gene=entry.gene,
                category=entry.category,
                trait=entry.trait,
                genotype=vcf_var.genotype,
                alleles=vcf_var.gt_alleles,
                risk_allele=entry.risk_allele,
                risk_allele_count=risk_allele_count,
                evidence_grade=entry.evidence_grade,
                found_in_vcf=True,
            )
        )

    logger.info(
        "Extracted %d features (%d found in VCF)",
        len(features),
        sum(1 for f in features if f.found_in_vcf),
    )
    return features
