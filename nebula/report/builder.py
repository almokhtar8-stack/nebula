"""
Report builder.

Assembles all pipeline outputs into the structured NebulaReport JSON
matching the Deliverable 4 report template (Sections A–J).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from nebula.schemas import (
    EvidenceEntry,
    EvidenceGrade,
    GeneticFeature,
    NebulaReport,
    NextStep,
    OutputTier,
    PRSScore,
    ReportSummary,
    RuleCategory,
    RuleResult,
    SampleQCResult,
    UserMetadata,
)

PIPELINE_VERSION = "0.1.0"

FIXED_DISCLAIMERS = [
    (
        "This report is not a medical diagnosis. It does not diagnose, treat, "
        "cure, or prevent any disease."
    ),
    (
        "Genetic predisposition is not destiny. Your genes influence tendencies "
        "and probabilities; they do not determine outcomes. Lifestyle, environment, "
        "diet, exercise, sleep, stress management, and medical care all play "
        "significant and often dominant roles."
    ),
    (
        "Polygenic risk scores reflect your position in a population distribution. "
        "They do not predict with certainty whether you will or will not develop a "
        "condition. A high-risk score means higher inherited predisposition relative "
        "to the reference population, not a guaranteed outcome."
    ),
    (
        "Pharmacogenomic results describe how your body may metabolize certain "
        "medications. They are not prescribing advice. Share these results with your "
        "physician or pharmacist, who can integrate them with your full medical context."
    ),
    (
        "This report does not replace consultation with a physician, registered "
        "dietitian, genetic counselor, or mental health professional. If any finding "
        "concerns you, please discuss it with an appropriate healthcare provider."
    ),
    (
        "The science of genomics is evolving. Some findings in this report may be "
        "updated as new research emerges. We recommend periodic re-evaluation."
    ),
    (
        "This report was generated using synthetic demonstration data and is "
        "for development and testing purposes only. It must not be used for "
        "clinical decision-making."
    ),
]


def _build_next_steps(
    rule_results: list[RuleResult],
    prs_scores: list[PRSScore],
    metadata: UserMetadata,
) -> list[NextStep]:
    """Derive follow-up actions from triggered rules and PRS findings."""
    steps: list[NextStep] = []
    seen: set[str] = set()

    def add(action: str, reason: str, urgency: str) -> None:
        key = action[:60]
        if key not in seen:
            seen.add(key)
            steps.append(NextStep(action=action, reason=reason, urgency=urgency))

    for rule in rule_results:
        if rule.output_tier == OutputTier.TIER_3:
            add(
                "Request genetic counselor review before report release.",
                f"Rule {rule.rule_id} triggered a Tier 3 (clinical referral) finding.",
                "urgent",
            )
        elif rule.referral_trigger:
            add(
                "Discuss this report with your physician, especially the flagged items.",
                "One or more findings carry a physician-discussion referral trigger.",
                "recommended",
            )

    for prs in prs_scores:
        if prs.percentile >= 80:
            if prs.condition == "CAD":
                add(
                    "Request a lipid panel (LDL, HDL, triglycerides) if not done recently.",
                    f"CAD PRS at {prs.percentile:.0f}th percentile.",
                    "recommended",
                )
            elif prs.condition == "T2D":
                add(
                    "Request HbA1c and fasting glucose if not recently tested.",
                    f"T2D PRS at {prs.percentile:.0f}th percentile.",
                    "recommended",
                )
            elif prs.condition == "BrCa":
                add(
                    "Ensure adherence to recommended mammography screening schedule.",
                    f"Breast cancer PRS at {prs.percentile:.0f}th percentile.",
                    "recommended",
                )

    for rule in rule_results:
        if rule.rule_id == "NUT-008":
            add(
                "Request 25(OH)D (vitamin D) blood test.",
                "Multiple low-vitamin-D risk alleles detected.",
                "routine",
            )
        if rule.rule_id == "NUT-007":
            add(
                "Request serum ferritin and transferrin saturation.",
                "HFE C282Y homozygosity detected — monitor for iron overload.",
                "recommended",
            )

    add(
        "Re-submit your lifestyle questionnaire in 6 months to refine recommendations.",
        "Lifestyle data is time-sensitive; updated answers may change recommendations.",
        "routine",
    )

    if metadata.pregnancy_planning:
        add(
            "Discuss folate supplementation dosing with your physician.",
            "Pregnancy planning flag set in questionnaire.",
            "recommended",
        )

    return steps


def build_report(
    metadata: UserMetadata,
    qc_result: SampleQCResult,
    features: list[GeneticFeature],
    prs_scores: list[PRSScore],
    rule_results: list[RuleResult],
    ruleset_version: str,
) -> NebulaReport:
    """Assemble the full NebulaReport from all pipeline outputs."""
    now = datetime.now(timezone.utc).isoformat()
    report_id = str(uuid.uuid4())

    by_category: dict[str, list[RuleResult]] = {c.value: [] for c in RuleCategory}
    for r in rule_results:
        by_category[r.category.value].append(r)

    watchlist = [
        r for r in rule_results
        if r.output_tier in (OutputTier.TIER_2, OutputTier.TIER_3)
    ]

    referral_triggers = [r.rule_id for r in rule_results if r.referral_trigger]

    evidence_table = [
        EvidenceEntry(
            recommendation_id=r.rule_id,
            evidence_grade=r.evidence_grade,
            confidence_score=r.confidence_score,
            data_sources=r.data_sources,
        )
        for r in rule_results
    ]

    strong_count = sum(1 for r in rule_results if r.evidence_grade == EvidenceGrade.STRONG)
    moderate_count = sum(1 for r in rule_results if r.evidence_grade == EvidenceGrade.MODERATE)
    exploratory_count = sum(
        1 for r in rule_results if r.evidence_grade == EvidenceGrade.EXPLORATORY
    )

    top = sorted(
        [r for r in rule_results if r.output_tier != OutputTier.TIER_3],
        key=lambda x: x.confidence_score,
        reverse=True,
    )[:3]
    top_insight_texts = [r.recommendation_text[:120] + "..." for r in top]

    summary = ReportSummary(
        sample_id=metadata.sample_id,
        report_version="1.0",
        generated_at=now,
        total_insights=len(rule_results),
        strong_evidence_count=strong_count,
        moderate_evidence_count=moderate_count,
        exploratory_count=exploratory_count,
        referral_triggers=referral_triggers,
        top_insights=top_insight_texts,
    )

    next_steps = _build_next_steps(rule_results, prs_scores, metadata)

    qc_dict = {
        "sample_id": qc_result.sample_id,
        "genome_build": qc_result.genome_build.value,
        "total_variants": qc_result.total_variants,
        "call_rate": round(qc_result.call_rate, 4),
        "het_rate": round(qc_result.het_rate, 4),
        "whitelist_coverage": round(qc_result.whitelist_coverage, 4),
        "overall_pass": qc_result.overall_pass,
        "warnings": qc_result.warnings,
        "errors": qc_result.errors,
    }

    return NebulaReport(
        report_id=report_id,
        sample_id=metadata.sample_id,
        generated_at=now,
        pipeline_version=PIPELINE_VERSION,
        ruleset_version=ruleset_version,
        summary=summary,
        insights=by_category,
        watchlist=watchlist,
        evidence_confidence=evidence_table,
        next_steps=next_steps,
        disclaimers=FIXED_DISCLAIMERS,
        qc_summary=qc_dict,
        prs_scores=prs_scores,
    )
