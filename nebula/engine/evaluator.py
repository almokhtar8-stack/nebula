"""
Deterministic rule evaluator.

Applies each rule from the loaded YAML ruleset against the resolved
genetic features and user metadata. All logic is explicit IF/THEN —
no probabilistic inference, no ML, no LLM calls.

Each rule's trigger is evaluated by a named condition function
keyed to the rule's `trigger` string in the YAML.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from nebula.schemas import (
    EvidenceGrade,
    GeneticFeature,
    OutputTier,
    PRSScore,
    RuleCategory,
    RuleResult,
    UserMetadata,
)

logger = logging.getLogger(__name__)

# Feature lookup type
FeatureMap = dict[str, GeneticFeature]
PRSMap = dict[str, PRSScore]

# ---------------------------------------------------------------------------
# Trigger condition functions
#
# Each function receives (features: FeatureMap, prs: PRSMap, meta: UserMetadata)
# and returns True/False indicating whether the rule fires.
#
# Adding a new rule = add an entry to TRIGGER_CONDITIONS below.
# Nothing else in code needs to change.
# ---------------------------------------------------------------------------

TriggerFn = Callable[[FeatureMap, PRSMap, UserMetadata], bool]

TRIGGER_CONDITIONS: dict[str, TriggerFn] = {}


def _register(name: str) -> Callable[[TriggerFn], TriggerFn]:
    def decorator(fn: TriggerFn) -> TriggerFn:
        TRIGGER_CONDITIONS[name] = fn
        return fn
    return decorator


# ── Fitness ──────────────────────────────────────────────────────────────────

@_register("FIT-001")
def _fit_001(f: FeatureMap, _p: PRSMap, m: UserMetadata) -> bool:
    actn3 = f.get("rs1815739")
    if actn3 is None or not actn3.found_in_vcf:
        return False
    # XX = homozygous stop = genotype with 0 risk (R) alleles
    # Risk allele in whitelist = "C" (stop codon); ref = "T" (Arg)
    # XX means 0 copies of T (Arg) allele = 2 copies of C (stop)
    is_xx = actn3.genotype in ("CC",) or (
        actn3.risk_allele_count == 2
    )
    has_endurance = any(
        g.value in ("endurance", "general_wellness") for g in m.exercise_goals
    )
    return is_xx and has_endurance


@_register("FIT-002")
def _fit_002(f: FeatureMap, _p: PRSMap, m: UserMetadata) -> bool:
    actn3 = f.get("rs1815739")
    if actn3 is None or not actn3.found_in_vcf:
        return False
    is_rr = actn3.risk_allele_count == 0  # 0 stop alleles = full alpha-actinin-3
    has_power = any(g.value in ("strength", "power") for g in m.exercise_goals)
    return is_rr and has_power


@_register("FIT-003")
def _fit_003(f: FeatureMap, _p: PRSMap, m: UserMetadata) -> bool:
    col5a1 = f.get("rs12722")
    if col5a1 is None or not col5a1.found_in_vcf:
        return False
    has_risk = col5a1.risk_allele_count >= 1
    high_impact = any(
        t in m.exercise_types for t in ["running", "jumping", "hiit", "crossfit"]
    ) or m.training_frequency_per_week >= 4
    return has_risk and high_impact


@_register("FIT-004")
def _fit_004(f: FeatureMap, _p: PRSMap, m: UserMetadata) -> bool:
    il6 = f.get("rs1800795")
    if il6 is None or not il6.found_in_vcf:
        return False
    is_gg = il6.genotype == "GG" or il6.risk_allele_count == 2
    return is_gg and m.training_frequency_per_week >= 5


# ── Nutrition ─────────────────────────────────────────────────────────────────

@_register("NUT-001")
def _nut_001(f: FeatureMap, _p: PRSMap, _m: UserMetadata) -> bool:
    cyp = f.get("rs762551")
    if cyp is None or not cyp.found_in_vcf:
        return False
    # Slow metabolizer = AC or CC (C is the slow allele)
    return cyp.risk_allele_count >= 1


@_register("NUT-002")
def _nut_002(f: FeatureMap, _p: PRSMap, _m: UserMetadata) -> bool:
    lct = f.get("rs4988235")
    if lct is None or not lct.found_in_vcf:
        return False
    # TT = lactase non-persistence (T is non-persistence allele)
    return lct.risk_allele_count == 2


@_register("NUT-003")
def _nut_003(f: FeatureMap, _p: PRSMap, _m: UserMetadata) -> bool:
    mthfr = f.get("rs1801133")
    if mthfr is None or not mthfr.found_in_vcf:
        return False
    # TT = homozygous C677T (T is the variant allele)
    return mthfr.risk_allele_count == 2


@_register("NUT-004")
def _nut_004(f: FeatureMap, _p: PRSMap, m: UserMetadata) -> bool:
    aldh2 = f.get("rs671")
    if aldh2 is None or not aldh2.found_in_vcf:
        return False
    # GA or AA (A is the deficiency allele)
    return aldh2.risk_allele_count >= 1


@_register("NUT-005")
def _nut_005(f: FeatureMap, _p: PRSMap, _m: UserMetadata) -> bool:
    fto = f.get("rs9939609")
    if fto is None or not fto.found_in_vcf:
        return False
    # AA = risk homozygote (A is risk allele)
    return fto.risk_allele_count == 2


@_register("NUT-006")
def _nut_006(f: FeatureMap, _p: PRSMap, _m: UserMetadata) -> bool:
    fads1 = f.get("rs174546")
    if fads1 is None or not fads1.found_in_vcf:
        return False
    # TT = reduced converter (T is reduced-activity allele)
    return fads1.risk_allele_count == 2


@_register("NUT-007")
def _nut_007(f: FeatureMap, _p: PRSMap, _m: UserMetadata) -> bool:
    hfe = f.get("rs1800562")
    if hfe is None or not hfe.found_in_vcf:
        return False
    # AA = homozygous C282Y (A is risk allele)
    return hfe.risk_allele_count == 2


@_register("NUT-008")
def _nut_008(f: FeatureMap, _p: PRSMap, _m: UserMetadata) -> bool:
    gc = f.get("rs2282679")
    cyp2r1 = f.get("rs10741657")
    dhcr7 = f.get("rs12785878")
    risk_allele_count = 0
    for feat in [gc, cyp2r1, dhcr7]:
        if feat and feat.found_in_vcf:
            risk_allele_count += feat.risk_allele_count
    return risk_allele_count >= 3


# ── Recovery / Sleep ──────────────────────────────────────────────────────────

@_register("REC-001")
def _rec_001(f: FeatureMap, _p: PRSMap, m: UserMetadata) -> bool:
    per2 = f.get("rs2304672")
    clock = f.get("rs1801260")
    evening_tendency = 0
    for feat in [per2, clock]:
        if feat and feat.found_in_vcf:
            evening_tendency += feat.risk_allele_count
    return evening_tendency >= 1 and m.schedule_requires_early_wake


@_register("REC-002")
def _rec_002(f: FeatureMap, _p: PRSMap, _m: UserMetadata) -> bool:
    ada = f.get("rs73598374")
    if ada is None or not ada.found_in_vcf:
        return False
    # Asn/Asn = homozygous (risk allele = Asn variant)
    return ada.risk_allele_count == 2


@_register("REC-003")
def _rec_003(f: FeatureMap, _p: PRSMap, m: UserMetadata) -> bool:
    cyp = f.get("rs762551")
    if cyp is None or not cyp.found_in_vcf:
        return False
    slow = cyp.risk_allele_count >= 1
    high_caffeine = m.caffeine_mg_per_day > 200
    poor_sleep = m.sleep_quality.value == "poor"
    return slow and high_caffeine and poor_sleep


# ── Health Risk ───────────────────────────────────────────────────────────────

@_register("RISK-001")
def _risk_001(_f: FeatureMap, p: PRSMap, _m: UserMetadata) -> bool:
    cad = p.get("CAD")
    return cad is not None and cad.percentile >= 80.0


@_register("RISK-002")
def _risk_002(_f: FeatureMap, p: PRSMap, _m: UserMetadata) -> bool:
    t2d = p.get("T2D")
    return t2d is not None and t2d.percentile >= 80.0


@_register("RISK-003")
def _risk_003(_f: FeatureMap, p: PRSMap, m: UserMetadata) -> bool:
    brca = p.get("BrCa")
    return (
        brca is not None
        and brca.percentile >= 80.0
        and m.sex_biological.value == "female"
    )


@_register("RISK-004")
def _risk_004(f: FeatureMap, _p: PRSMap, _m: UserMetadata) -> bool:
    slco = f.get("rs4149056")
    if slco is None or not slco.found_in_vcf:
        return False
    return slco.risk_allele_count == 2  # CC genotype


@_register("RISK-005")
def _risk_005(f: FeatureMap, _p: PRSMap, _m: UserMetadata) -> bool:
    dpyd = f.get("rs3918290")
    if dpyd is None or not dpyd.found_in_vcf:
        return False
    return dpyd.risk_allele_count >= 1  # heterozygous or homozygous carrier


@_register("RISK-006")
def _risk_006(f: FeatureMap, _p: PRSMap, m: UserMetadata) -> bool:
    hla_dq2 = f.get("rs2187668")   # HLA-DQ2.5 proxy
    hla_dq8 = f.get("rs7454108")   # HLA-DQ8 proxy
    hla_positive = (
        (hla_dq2 and hla_dq2.found_in_vcf and hla_dq2.risk_allele_count >= 1)
        or (hla_dq8 and hla_dq8.found_in_vcf and hla_dq8.risk_allele_count >= 1)
    )
    return hla_positive and m.gi_symptoms


# ---------------------------------------------------------------------------
# Confidence score computation
# ---------------------------------------------------------------------------


def _compute_confidence(
    base: int,
    adjustments: list[dict[str, Any]],
    features: FeatureMap,
    prs: PRSMap,
    meta: UserMetadata,
) -> int:
    """Apply confidence_adjustments from YAML rule to base score."""
    score = base

    for adj in adjustments:
        condition = adj.get("condition", "")
        delta = adj.get("delta", 0)

        # Evaluate simple conditions
        matched = False
        if condition == "has_endurance_goal":
            matched = any(g.value in ("endurance",) for g in meta.exercise_goals)
        elif condition == "has_strength_goal":
            matched = any(g.value in ("strength", "power") for g in meta.exercise_goals)
        elif condition == "no_questionnaire":
            matched = False  # questionnaire always present in MVP
        elif condition == "training_frequency_gte_5":
            matched = meta.training_frequency_per_week >= 5
        elif condition == "poor_sleep":
            matched = meta.sleep_quality.value == "poor"
        elif condition == "gi_symptoms":
            matched = meta.gi_symptoms
        elif condition == "family_history_cvd":
            matched = meta.family_history_cvd
        elif condition == "family_history_breast_cancer":
            matched = meta.family_history_breast_cancer
        elif condition == "fat_loss_goal":
            matched = any(g.value == "fat_loss" for g in meta.exercise_goals)
        elif condition == "vegan_or_vegetarian":
            matched = meta.diet_type.value in ("vegan", "vegetarian")
        elif condition == "restrictive_diet":
            matched = meta.diet_type.value in ("vegan", "keto", "paleo")
        elif condition == "ancestry_mismatch_cad":
            cad = prs.get("CAD")
            matched = cad is not None and not cad.ancestry_match_flag
        elif condition == "ancestry_mismatch_t2d":
            t2d = prs.get("T2D")
            matched = t2d is not None and not t2d.ancestry_match_flag
        elif condition == "ancestry_mismatch_brca":
            brca = prs.get("BrCa")
            matched = brca is not None and not brca.ancestry_match_flag
        elif condition == "sedentary_and_elevated_bmi":
            matched = meta.training_frequency_per_week <= 1
        elif condition == "high_caffeine":
            matched = meta.caffeine_mg_per_day > 200
        elif condition == "chronotype_schedule_mismatch":
            matched = meta.schedule_requires_early_wake
        elif condition == "low_sun_or_northern_latitude":
            matched = (
                meta.sun_exposure_hours_per_day is not None
                and meta.sun_exposure_hours_per_day < 1
            ) or (
                meta.latitude_degrees is not None
                and abs(meta.latitude_degrees) > 45
            )

        if matched:
            score += delta

    return max(0, min(100, score))


# ---------------------------------------------------------------------------
# Main evaluator
# ---------------------------------------------------------------------------


def evaluate_rules(
    ruleset: dict[str, Any],
    features: list[GeneticFeature],
    prs_scores: list[PRSScore],
    metadata: UserMetadata,
) -> list[RuleResult]:
    """
    Apply all rules in the ruleset against the provided features and metadata.

    Only triggered rules are returned (triggered=True).
    """
    feature_map: FeatureMap = {f.rsid: f for f in features}
    prs_map: PRSMap = {p.condition: p for p in prs_scores}

    ruleset_version: str = str(ruleset.get("version", "unknown"))
    results: list[RuleResult] = []

    for rule in ruleset["rules"]:
        rule_id: str = rule["id"]
        trigger_fn = TRIGGER_CONDITIONS.get(rule_id)

        if trigger_fn is None:
            logger.warning("No trigger function registered for rule '%s'; skipping", rule_id)
            continue

        try:
            triggered = trigger_fn(feature_map, prs_map, metadata)
        except Exception as exc:
            logger.error("Error evaluating trigger for rule '%s': %s", rule_id, exc)
            continue

        if not triggered:
            continue

        base_confidence: int = rule.get("base_confidence", 50)
        adjustments: list[dict[str, Any]] = rule.get("confidence_adjustments", [])
        confidence = _compute_confidence(
            base_confidence, adjustments, feature_map, prs_map, metadata
        )

        try:
            category = RuleCategory(rule["category"])
        except ValueError:
            category = RuleCategory.FITNESS

        try:
            evidence_grade = EvidenceGrade(rule["evidence_grade"])
        except ValueError:
            evidence_grade = EvidenceGrade.EXPLORATORY

        try:
            output_tier = OutputTier(rule["output_tier"])
        except ValueError:
            output_tier = OutputTier.TIER_1

        # Build data_sources list dynamically
        data_sources: list[str] = rule.get("data_sources", [])

        results.append(
            RuleResult(
                rule_id=rule_id,
                category=category,
                triggered=True,
                recommendation_text=rule["recommendation_text"],
                reason=rule["reason"],
                data_sources=data_sources,
                evidence_grade=evidence_grade,
                confidence_score=confidence,
                practical_action=rule["practical_action"],
                review_interval=rule["review_interval"],
                disclaimer=rule["disclaimer"],
                referral_trigger=bool(rule.get("referral_trigger", False)),
                output_tier=output_tier,
                rule_version=ruleset_version,
            )
        )
        logger.debug("Rule %s triggered (confidence=%d)", rule_id, confidence)

    logger.info(
        "%d of %d rules triggered",
        len(results),
        len(ruleset["rules"]),
    )
    return results
