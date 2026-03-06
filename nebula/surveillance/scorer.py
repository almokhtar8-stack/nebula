"""
Evidence scorer.

Applies deterministic rules to score surveillance candidates.
This is the same philosophy as the main rule engine — IF/THEN logic,
no ML, fully auditable.

The scoring thresholds are loaded from surveillance_config.yml so a
genetic counselor can adjust them without touching code.
"""

from __future__ import annotations

import logging
from typing import Any

from nebula.surveillance.models import (
    EvidenceSignal,
    GWASHit,
    PubMedPaper,
    SurveillanceCandidate,
    DataSource,
)
from nebula.whitelist.extractor import WhitelistEntry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default scoring thresholds
# These are overridden by surveillance_config.yml if present
# ---------------------------------------------------------------------------

DEFAULT_THRESHOLDS: dict[str, Any] = {
    "strong_candidate": {
        "min_sample_size": 50_000,
        "min_replication_studies": 2,
        "max_p_value": 5e-8,
        "min_auto_score": 70,
    },
    "moderate_candidate": {
        "min_sample_size": 10_000,
        "min_replication_studies": 1,
        "max_p_value": 5e-8,
        "min_auto_score": 40,
    },
    "contradiction": {
        "null_replication_keywords": [
            "did not replicate",
            "failed to replicate",
            "no significant association",
            "null result",
            "non-significant",
            "not replicated",
            "lack of replication",
        ]
    }
}


def _score_gwas_hits(
    hits: list[GWASHit],
    thresholds: dict[str, Any],
) -> tuple[int, list[str]]:
    """
    Score a list of GWAS hits. Returns (score 0-100, list of reasons).
    """
    score = 0
    reasons: list[str] = []

    if not hits:
        return 0, ["No GWAS Catalog associations found"]

    # Best hit (lowest p-value)
    best = min(hits, key=lambda h: h.p_value)

    # P-value
    if best.p_value <= 1e-10:
        score += 25
        reasons.append(f"p-value {best.p_value:.2e} — very strong signal")
    elif best.p_value <= 5e-8:
        score += 15
        reasons.append(f"p-value {best.p_value:.2e} — genome-wide significant")

    # Sample size
    max_n = max((h.sample_size for h in hits), default=0)
    if max_n >= 100_000:
        score += 25
        reasons.append(f"Largest study n={max_n:,} — biobank scale")
    elif max_n >= 50_000:
        score += 20
        reasons.append(f"Largest study n={max_n:,}")
    elif max_n >= 10_000:
        score += 10
        reasons.append(f"Largest study n={max_n:,}")
    else:
        reasons.append(f"Small sample size n={max_n:,} — caution")

    # Number of independent studies (replication proxy)
    n_studies = len(hits)
    if n_studies >= 5:
        score += 25
        reasons.append(f"{n_studies} independent GWAS associations — well replicated")
    elif n_studies >= 3:
        score += 20
        reasons.append(f"{n_studies} independent associations")
    elif n_studies >= 2:
        score += 10
        reasons.append(f"{n_studies} associations — initial replication")
    else:
        reasons.append("Only 1 association — not yet independently replicated")

    # Ancestry diversity
    ancestries = {h.ancestry for h in hits if h.ancestry}
    if len(ancestries) >= 3:
        score += 15
        reasons.append(f"Multi-ancestry evidence: {', '.join(list(ancestries)[:3])}")
    elif len(ancestries) == 2:
        score += 8
        reasons.append("Evidence in 2 ancestry groups")
    else:
        reasons.append("Single ancestry — generalisability limited")

    # Effect size (beta or OR) — existence check
    hits_with_effect = [h for h in hits if h.beta_or_or is not None]
    if hits_with_effect:
        score += 10
        best_effect = hits_with_effect[0].beta_or_or
        reasons.append(f"Effect size reported: {best_effect:.3f}")

    return min(score, 100), reasons


def _check_contradiction(
    papers: list[PubMedPaper],
    thresholds: dict[str, Any],
) -> tuple[bool, str]:
    """
    Scan paper titles for null/contradiction signals.
    Returns (is_contradiction, reason).
    """
    keywords = thresholds.get("contradiction", {}).get(
        "null_replication_keywords", DEFAULT_THRESHOLDS["contradiction"]["null_replication_keywords"]
    )

    for paper in papers:
        title_lower = paper.title.lower()
        abstract_lower = paper.abstract.lower()
        for kw in keywords:
            if kw in title_lower or kw in abstract_lower:
                return True, f"Paper '{paper.title[:80]}' contains null signal: '{kw}'"

    return False, ""


def score_candidate(
    rsid: str,
    trait: str,
    gene: str,
    gwas_hits: list[GWASHit],
    papers: list[PubMedPaper],
    existing_whitelist: dict[str, WhitelistEntry],
    thresholds: dict[str, Any] | None = None,
    candidate_id: str | None = None,
) -> SurveillanceCandidate:
    """
    Score a surveillance candidate and return a SurveillanceCandidate.

    This is the core function that converts raw API data into a
    structured review queue entry.
    """
    t = thresholds or DEFAULT_THRESHOLDS
    strong_t = t.get("strong_candidate", DEFAULT_THRESHOLDS["strong_candidate"])
    moderate_t = t.get("moderate_candidate", DEFAULT_THRESHOLDS["moderate_candidate"])

    # Score GWAS hits
    gwas_score, gwas_reasons = _score_gwas_hits(gwas_hits, t)

    # Paper count bonus
    paper_bonus = min(len(papers) * 2, 10)
    total_score = min(gwas_score + paper_bonus, 100)

    all_reasons = gwas_reasons.copy()
    if papers:
        all_reasons.append(f"{len(papers)} PubMed papers found")

    # Check for contradictions
    is_contradiction, contradiction_reason = _check_contradiction(papers, t)
    if is_contradiction:
        all_reasons.append(f"⚠ CONTRADICTION SIGNAL: {contradiction_reason}")

    # Determine signal
    already_in_whitelist = rsid in existing_whitelist
    existing_grade = (
        existing_whitelist[rsid].evidence_grade.value
        if already_in_whitelist
        else None
    )

    if is_contradiction and already_in_whitelist:
        signal = EvidenceSignal.CONTRADICTS_EXISTING
    elif total_score >= strong_t.get("min_auto_score", 70):
        signal = EvidenceSignal.STRONG_CANDIDATE
    elif total_score >= moderate_t.get("min_auto_score", 40):
        signal = EvidenceSignal.MODERATE_CANDIDATE
    elif gwas_hits or papers:
        signal = EvidenceSignal.WEAK
    else:
        signal = EvidenceSignal.INSUFFICIENT_DATA

    cid = candidate_id or f"surv_{rsid}_{hash(trait) % 100000:05d}"

    return SurveillanceCandidate(
        candidate_id=cid,
        source=DataSource.GWAS_CATALOG if gwas_hits else DataSource.PUBMED,
        rsid=rsid,
        trait=trait,
        gene=gene,
        signal=signal,
        auto_score=total_score,
        score_reasons=all_reasons,
        gwas_hits=gwas_hits,
        pubmed_papers=papers,
        already_in_whitelist=already_in_whitelist,
        existing_evidence_grade=existing_grade,
        contradicts_existing=is_contradiction,
    )
