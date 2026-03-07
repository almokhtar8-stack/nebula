"""
nebula.whitelist.extractor – Load the variant whitelist and resolve it
against a user's parsed VCF variants.

Fixed to produce GeneticFeature (from nebula.schemas) with:
  - found_in_vcf correctly set
  - risk_allele_count computed from gt_alleles vs whitelist risk_allele
  - genotype as string (e.g. "CT")
"""
from __future__ import annotations

import csv
from pathlib import Path

from nebula.schemas import EvidenceGrade, GeneticFeature, RawVariant


class WhitelistLoadError(ValueError):
    pass


class WhitelistEntry:
    """Minimal whitelist entry — holds all columns from the CSV."""
    __slots__ = ("rsid", "gene", "category", "trait", "risk_allele",
                 "ref_allele", "evidence_grade", "chrom", "pos", "notes")

    def __init__(self, rsid, gene, category, trait, risk_allele,
                 ref_allele, evidence_grade, chrom="", pos=None, notes=""):
        self.rsid           = rsid
        self.gene           = gene
        self.category       = category
        self.trait          = trait
        self.risk_allele    = risk_allele or ""
        self.ref_allele     = ref_allele or ""
        self.evidence_grade = evidence_grade
        self.chrom          = chrom
        self.pos            = pos
        self.notes          = notes


def _parse_evidence_grade(raw: str) -> EvidenceGrade:
    mapping = {
        "strong":         EvidenceGrade.STRONG,
        "moderate":       EvidenceGrade.MODERATE,
        "weak_moderate":  EvidenceGrade.MODERATE,
        "exploratory":    EvidenceGrade.EXPLORATORY,
        "weak":           EvidenceGrade.EXPLORATORY,
    }
    return mapping.get(raw.lower().strip(), EvidenceGrade.EXPLORATORY)


def load_whitelist(whitelist_path: Path) -> dict[str, WhitelistEntry]:
    """Load whitelist CSV → {rsid: WhitelistEntry}."""
    required_cols = {"rsid", "gene", "trait", "category", "evidence_grade"}
    entries: dict[str, WhitelistEntry] = {}

    with open(whitelist_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise WhitelistLoadError("Whitelist CSV is empty or has no header row.")
        col_set = {c.strip().lower() for c in reader.fieldnames}
        missing = required_cols - col_set
        if missing:
            raise WhitelistLoadError(f"Whitelist CSV missing columns: {missing}")

        for row in reader:
            row = {k.strip().lower(): v.strip() for k, v in row.items()}
            rsid = row["rsid"]
            if not rsid:
                continue
            entries[rsid] = WhitelistEntry(
                rsid=rsid,
                gene=row["gene"],
                category=row["category"],
                trait=row["trait"],
                risk_allele=row.get("risk_allele", "") or "",
                ref_allele=row.get("ref_allele", "") or "",
                evidence_grade=_parse_evidence_grade(row["evidence_grade"]),
                chrom=row.get("chrom", ""),
                pos=int(row["pos"]) if row.get("pos") else None,
                notes=row.get("notes", ""),
            )

    if not entries:
        raise WhitelistLoadError("Whitelist CSV contains no entries.")
    return entries


def whitelist_rsids(whitelist: dict[str, WhitelistEntry]) -> set[str]:
    """Return the set of rsIDs in the whitelist."""
    return set(whitelist.keys())


def extract_features(
    whitelist: dict[str, WhitelistEntry],
    variants: list[RawVariant],
) -> list[GeneticFeature]:
    """
    Match VCF variants to whitelist entries.
    Returns GeneticFeature objects with:
      - found_in_vcf=True for all variants (absent in WGS = hom ref)
      - risk_allele_count computed from actual alleles vs whitelist risk allele
      - genotype as sorted allele string (e.g. "CT")
    """
    # Index VCF variants by rsID (skip missing/no-call genotypes)
    vcf_by_rsid: dict[str, RawVariant] = {
        v.rsid: v
        for v in variants
        if v.rsid and v.genotype != "missing" and v.gt_alleles
    }

    features: list[GeneticFeature] = []

    for rsid, entry in whitelist.items():
        vcf_var = vcf_by_rsid.get(rsid)

        if vcf_var is None:
            # Absent from WGS VCF = homozygous reference (ref/ref).
            # WGS only records sites that differ from reference — absence
            # means 0 copies of the alt/risk allele, not missing data.
            ref_allele  = entry.ref_allele or ""
            risk_allele = entry.risk_allele or ""
            hom_ref_alleles  = [ref_allele, ref_allele] if ref_allele else []
            hom_ref_genotype = ref_allele * 2 if ref_allele else ""
            features.append(GeneticFeature(
                rsid=rsid,
                gene=entry.gene,
                category=entry.category,
                trait=entry.trait,
                genotype=hom_ref_genotype,
                alleles=hom_ref_alleles,
                risk_allele=risk_allele,
                risk_allele_count=0,
                evidence_grade=entry.evidence_grade,
                found_in_vcf=True,   # treat as known homozygous reference
            ))
        else:
            alleles     = vcf_var.gt_alleles    # e.g. ["G", "A"] from VCF
            risk_allele = entry.risk_allele     # e.g. "T" from whitelist
            ref_allele  = entry.ref_allele      # e.g. "C" from whitelist

            # Strand-flip: 1000G sometimes reports reverse-complement alleles.
            # Detect by checking if VCF REF is the complement of whitelist REF.
            COMP = {"A": "T", "T": "A", "C": "G", "G": "C"}
            vcf_ref = vcf_var.ref
            if (ref_allele and vcf_ref
                    and vcf_ref != ref_allele
                    and COMP.get(vcf_ref, "") == ref_allele):
                alleles = [COMP.get(a, a) for a in alleles]

            risk_count   = sum(1 for a in alleles if a == risk_allele)
            genotype_str = "".join(sorted(alleles))

            features.append(GeneticFeature(
                rsid=rsid,
                gene=entry.gene,
                category=entry.category,
                trait=entry.trait,
                genotype=genotype_str,
                alleles=alleles,
                risk_allele=risk_allele,
                risk_allele_count=risk_count,
                evidence_grade=entry.evidence_grade,
                found_in_vcf=True,
            ))

    return features
