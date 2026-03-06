"""
nebula.whitelist.extractor – Load the variant whitelist and resolve it
against a user's parsed VCF variants.
"""
from __future__ import annotations

import csv
from pathlib import Path

from ..models import EvidenceGrade, GenotypeCall, RawVariant, VariantFeature, WhitelistEntry


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


def load_whitelist(whitelist_path: Path) -> dict[str, WhitelistEntry]:
    required_cols = {"rsid", "gene", "trait", "category", "evidence_grade"}
    entries: dict[str, WhitelistEntry] = {}

    with open(whitelist_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise WhitelistLoadError("Whitelist CSV is empty or has no header row.")
        col_set = {c.strip().lower() for c in reader.fieldnames}
        missing_cols = required_cols - col_set
        if missing_cols:
            raise WhitelistLoadError(f"Whitelist CSV is missing columns: {missing_cols}")

        for row in reader:
            row = {k.strip().lower(): v.strip() for k, v in row.items()}
            rsid = row["rsid"]
            if not rsid:
                continue
            entries[rsid] = WhitelistEntry(
                rsid=rsid,
                gene=row["gene"],
                chrom=row.get("chrom", ""),
                pos=int(row["pos"]) if row.get("pos") else None,
                ref=row.get("ref") or None,
                alt=row.get("alt") or None,
                risk_allele=row.get("risk_allele") or None,
                trait=row["trait"],
                category=row["category"],
                evidence_grade=_parse_evidence_grade(row["evidence_grade"]),
            )

    if not entries:
        raise WhitelistLoadError("Whitelist CSV contains no entries.")
    return entries


def extract_features(
    variants: list[RawVariant],
    whitelist: dict[str, WhitelistEntry],
) -> list[VariantFeature]:
    """
    Match VCF variants to whitelist entries.
    Whitelist entries absent from the VCF are recorded as MISSING.
    """
    vcf_by_rsid: dict[str, RawVariant] = {v.rsid: v for v in variants if v.rsid}

    features: list[VariantFeature] = []
    for rsid, entry in whitelist.items():
        vcf_var = vcf_by_rsid.get(rsid)
        if vcf_var is None:
            call = GenotypeCall.MISSING
            alt_count = 0
        else:
            call = vcf_var.call
            alt_count = vcf_var.alt_allele_count

        features.append(
            VariantFeature(
                rsid=rsid,
                gene=entry.gene,
                trait=entry.trait,
                category=entry.category,
                call=call,
                alt_allele_count=alt_count,
                evidence_grade=entry.evidence_grade,
            )
        )

    return features
