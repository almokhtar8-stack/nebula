"""
VCF ingestion and per-sample QC.

Handles VCF 4.x genotyping array output (single-sample).
No external network calls. No third-party bioinformatics tooling required
for MVP — parsing is pure Python against the spec's stated format.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from nebula.schemas import GenomeBuild, RawVariant, SampleQCResult

logger = logging.getLogger(__name__)

# QC thresholds (configurable, but safe defaults from Deliverable 5)
CALL_RATE_MIN = 0.95
HET_RATE_MIN = 0.20
HET_RATE_MAX = 0.35
MIN_GQ = 20


def _detect_genome_build(header_lines: list[str]) -> GenomeBuild:
    """Sniff genome build from VCF header. Defaults to GRCh37 if ambiguous."""
    for line in header_lines:
        lower = line.lower()
        if "grch38" in lower or "hg38" in lower:
            return GenomeBuild.GRCH38
        if "grch37" in lower or "hg19" in lower:
            return GenomeBuild.GRCH37
    logger.warning("Genome build not found in VCF header; defaulting to GRCh37")
    return GenomeBuild.GRCH37


def _extract_sample_id(header_lines: list[str]) -> str:
    """Extract sample ID from the #CHROM header line."""
    for line in header_lines:
        if line.startswith("#CHROM"):
            cols = line.strip().split("\t")
            if len(cols) >= 10:
                return cols[9]
            raise ValueError(
                "VCF #CHROM line has fewer than 10 columns — no sample column found."
            )
    raise ValueError("VCF is missing the required #CHROM header line.")


def _parse_genotype(gt_field: str, ref: str, alt: str) -> tuple[str, list[str]]:
    """
    Parse GT string (e.g. '0/1', '1/1', './.') into a normalised genotype
    string (e.g. 'AC') and a list of allele strings.
    Returns ('missing', []) for no-call.
    """
    allele_map = {".": None, "0": ref}
    for i, a in enumerate(alt.split(","), start=1):
        allele_map[str(i)] = a

    # Strip phase separator
    raw = re.split(r"[/|]", gt_field.split(":")[0])
    resolved: list[str] = []
    for token in raw:
        allele = allele_map.get(token)
        if allele is None:
            return "missing", []
        resolved.append(allele)

    resolved.sort()  # canonical ordering: alphabetical
    return "".join(resolved), resolved


def _parse_format_fields(
    format_str: str, sample_str: str
) -> dict[str, str]:
    """Zip FORMAT keys with SAMPLE values."""
    keys = format_str.split(":")
    vals = sample_str.split(":")
    return dict(zip(keys, vals, strict=False))


def parse_vcf(vcf_path: Path) -> tuple[str, GenomeBuild, list[RawVariant]]:
    """
    Parse a single-sample VCF file.

    Returns:
        (sample_id, genome_build, list[RawVariant])

    Raises:
        ValueError on format errors that prevent safe ingestion.
    """
    vcf_path = Path(vcf_path)
    if not vcf_path.exists():
        raise FileNotFoundError(f"VCF not found: {vcf_path}")

    header_lines: list[str] = []
    variants: list[RawVariant] = []
    sample_id: str | None = None
    genome_build: GenomeBuild | None = None

    with vcf_path.open("r") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n")

            # --- Header ---
            if line.startswith("#"):
                header_lines.append(line)
                if line.startswith("#CHROM"):
                    sample_id = _extract_sample_id(header_lines)
                    genome_build = _detect_genome_build(header_lines)
                continue

            # --- Data row ---
            cols = line.split("\t")
            if len(cols) < 10:
                logger.warning("Skipping malformed VCF line (< 10 cols): %s", line[:80])
                continue

            chrom, pos_str, vid, ref, alt, _qual, filt, _info, fmt, sample = cols[:10]

            try:
                pos = int(pos_str)
            except ValueError:
                logger.warning("Non-integer POS '%s'; skipping", pos_str)
                continue

            rsid: str | None = vid if vid.startswith("rs") else None
            filter_pass = filt in ("PASS", ".", "")

            fmt_fields = _parse_format_fields(fmt, sample)
            gt_raw = fmt_fields.get("GT", "./.")
            genotype_str, alleles = _parse_genotype(gt_raw, ref, alt)

            if genotype_str == "missing":
                variants.append(
                    RawVariant(
                        chrom=chrom,
                        pos=pos,
                        rsid=rsid,
                        ref=ref,
                        alt=alt,
                        genotype="missing",
                        gt_alleles=[],
                        filter_pass=False,
                    )
                )
                continue

            gq: int | None = None
            dp: int | None = None
            try:
                if "GQ" in fmt_fields and fmt_fields["GQ"] not in (".", ""):
                    gq = int(fmt_fields["GQ"])
                if "DP" in fmt_fields and fmt_fields["DP"] not in (".", ""):
                    dp = int(fmt_fields["DP"])
            except ValueError:
                pass

            # Apply GQ filter for sequencing data (arrays may not have GQ)
            if gq is not None and gq < MIN_GQ:
                filter_pass = False

            variants.append(
                RawVariant(
                    chrom=chrom,
                    pos=pos,
                    rsid=rsid,
                    ref=ref,
                    alt=alt,
                    genotype=genotype_str,
                    gt_alleles=alleles,
                    filter_pass=filter_pass,
                    gq=gq,
                    dp=dp,
                )
            )

    if sample_id is None:
        raise ValueError("Could not extract sample ID from VCF — #CHROM line missing.")
    if genome_build is None:
        genome_build = GenomeBuild.GRCH37

    logger.info("Parsed %d variants for sample %s", len(variants), sample_id)
    return sample_id, genome_build, variants


def run_qc(
    sample_id: str,
    genome_build: GenomeBuild,
    variants: list[RawVariant],
    whitelist_rsids: set[str],
) -> SampleQCResult:
    """
    Run per-sample QC checks per Deliverable 5 thresholds.

    Checks:
    - Call rate (non-missing genotypes / total)
    - Heterozygosity rate
    - Whitelist coverage (fraction of whitelist rsIDs present in VCF)
    """
    total = len(variants)
    if total == 0:
        return SampleQCResult(
            sample_id=sample_id,
            genome_build=genome_build,
            total_variants=0,
            pass_filter_variants=0,
            call_rate=0.0,
            call_rate_pass=False,
            het_rate=0.0,
            het_rate_pass=False,
            whitelist_coverage=0.0,
            whitelist_coverage_pass=False,
            errors=["VCF contains zero variant records."],
        )

    missing = sum(1 for v in variants if v.genotype == "missing")
    pass_filter = sum(1 for v in variants if v.filter_pass and v.genotype != "missing")
    called = total - missing
    call_rate = called / total

    het = sum(
        1
        for v in variants
        if v.filter_pass
        and len(set(v.gt_alleles)) == 2  # heterozygous: two distinct alleles
    )
    het_rate = het / called if called > 0 else 0.0

    # Whitelist coverage
    vcf_rsids = {v.rsid for v in variants if v.rsid and v.genotype != "missing"}
    if whitelist_rsids:
        found = len(whitelist_rsids & vcf_rsids)
        coverage = found / len(whitelist_rsids)
    else:
        coverage = 1.0  # no whitelist loaded; skip check

    warnings: list[str] = []
    errors: list[str] = []

    call_rate_pass = call_rate >= CALL_RATE_MIN
    het_rate_pass = HET_RATE_MIN <= het_rate <= HET_RATE_MAX
    coverage_pass = coverage >= 0.50  # warn below 50% whitelist coverage

    if not call_rate_pass:
        errors.append(
            f"Call rate {call_rate:.3f} is below minimum threshold {CALL_RATE_MIN}."
        )
    if not het_rate_pass:
        warnings.append(
            f"Heterozygosity rate {het_rate:.3f} outside expected range "
            f"[{HET_RATE_MIN}, {HET_RATE_MAX}]. May indicate sample contamination or "
            f"population outlier."
        )
    if not coverage_pass:
        warnings.append(
            f"Only {coverage:.1%} of whitelist rsIDs found in VCF. "
            f"Report may be incomplete. Check array compatibility."
        )

    return SampleQCResult(
        sample_id=sample_id,
        genome_build=genome_build,
        total_variants=total,
        pass_filter_variants=pass_filter,
        call_rate=call_rate,
        call_rate_pass=call_rate_pass,
        het_rate=het_rate,
        het_rate_pass=het_rate_pass,
        whitelist_coverage=coverage,
        whitelist_coverage_pass=coverage_pass,
        warnings=warnings,
        errors=errors,
    )
