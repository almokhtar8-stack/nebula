"""
PRS computation module.

For MVP, PRS is computed from a small set of sentinel variants with
published effect sizes. This is a simplified but scientifically
transparent implementation — real PRS uses genome-wide weights, but the
architecture and logic are identical.

Synthetic weights are used; do NOT use for clinical interpretation.
"""

from __future__ import annotations

import logging
import math

from nebula.schemas import GeneticFeature, PRSScore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Synthetic sentinel variant weights (illustration only — NOT clinical weights)
# Each entry: rsid -> {condition: weighted_effect}
#
# Real MVP would use published GWAS summary statistics (e.g., Inouye 2018
# for CAD, Mahajan 2018 for T2D). Weights are risk-allele log-OR equivalents.
# ---------------------------------------------------------------------------

PRS_WEIGHTS: dict[str, dict[str, float]] = {
    # CAD (Coronary Artery Disease)
    "rs1333049": {"CAD": 0.22},
    "rs10757278": {"CAD": 0.20},
    "rs2943634": {"CAD": 0.13},
    "rs9982601": {"CAD": 0.12},
    # T2D (Type 2 Diabetes)
    "rs7903146": {"T2D": 0.35},
    "rs1111875": {"T2D": 0.18},
    "rs5219": {"T2D": 0.16},
    "rs13266634": {"T2D": 0.14},
    # Breast Cancer (female-only)
    "rs2981582": {"BrCa": 0.28},
    "rs3803662": {"BrCa": 0.20},
    "rs889312": {"BrCa": 0.15},
    # Prostate Cancer (male-only)
    "rs1447295": {"PrCa": 0.30},
    "rs16901979": {"PrCa": 0.25},
    "rs6983267": {"PrCa": 0.18},
}

# Reference distributions: mean and std of raw PRS in a reference cohort
# (synthetic; real pipeline uses reference panel percentiles)
PRS_REFERENCE: dict[str, dict[str, float]] = {
    "CAD":  {"mean": 0.67, "std": 0.22},
    "T2D":  {"mean": 0.83, "std": 0.28},
    "BrCa": {"mean": 0.63, "std": 0.21},
    "PrCa": {"mean": 0.73, "std": 0.24},
}


def _normal_cdf(x: float) -> float:
    """Approximate standard normal CDF (Abramowitz & Stegun)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))


def _raw_to_percentile(raw: float, condition: str) -> float:
    """Convert raw PRS score to approximate percentile using reference distribution."""
    ref = PRS_REFERENCE.get(condition, {"mean": 0.5, "std": 0.2})
    z = (raw - ref["mean"]) / ref["std"]
    return round(_normal_cdf(z) * 100, 1)


def compute_prs(
    features: list[GeneticFeature],
    sex: str,
) -> list[PRSScore]:
    """
    Compute PRS scores for CAD, T2D, and sex-appropriate cancer scores.

    Args:
        features: Extracted genetic features with genotype info.
        sex: biological sex ("male" | "female" | "prefer_not_to_say")

    Returns:
        List of PRSScore objects.
    """
    # Build rsid -> risk_allele_count lookup
    feature_map: dict[str, GeneticFeature] = {
        f.rsid: f for f in features if f.found_in_vcf
    }

    # Accumulate raw PRS per condition
    raw_scores: dict[str, float] = {c: 0.0 for c in ["CAD", "T2D", "BrCa", "PrCa"]}
    alleles_found: dict[str, int] = {c: 0 for c in raw_scores}
    alleles_total: dict[str, int] = {c: 0 for c in raw_scores}

    for rsid, condition_weights in PRS_WEIGHTS.items():
        for condition, weight in condition_weights.items():
            alleles_total[condition] += 1
            feat = feature_map.get(rsid)
            if feat is not None:
                raw_scores[condition] += feat.risk_allele_count * weight
                alleles_found[condition] += 1

    results: list[PRSScore] = []

    for condition in ["CAD", "T2D"]:
        total = alleles_total[condition]
        found = alleles_found[condition]
        raw = raw_scores[condition]
        pct = _raw_to_percentile(raw, condition)
        ancestry_ok = found >= max(1, total // 2)  # warn if <50% of markers missing

        results.append(
            PRSScore(
                condition=condition,
                raw_score=round(raw, 4),
                percentile=pct,
                reference_population="European (synthetic reference)",
                ancestry_match_flag=ancestry_ok,
                note=(
                    ""
                    if ancestry_ok
                    else f"Only {found}/{total} PRS markers found — "
                    f"score may be less accurate."
                ),
            )
        )

    # Sex-specific cancers
    if sex == "female":
        raw = raw_scores["BrCa"]
        found = alleles_found["BrCa"]
        total = alleles_total["BrCa"]
        pct = _raw_to_percentile(raw, "BrCa")
        results.append(
            PRSScore(
                condition="BrCa",
                raw_score=round(raw, 4),
                percentile=pct,
                reference_population="Female European (synthetic reference)",
                ancestry_match_flag=found >= max(1, total // 2),
            )
        )
    elif sex == "male":
        raw = raw_scores["PrCa"]
        found = alleles_found["PrCa"]
        total = alleles_total["PrCa"]
        pct = _raw_to_percentile(raw, "PrCa")
        results.append(
            PRSScore(
                condition="PrCa",
                raw_score=round(raw, 4),
                percentile=pct,
                reference_population="Male European (synthetic reference)",
                ancestry_match_flag=found >= max(1, total // 2),
            )
        )

    logger.info("Computed PRS for conditions: %s", [r.condition for r in results])
    return results
