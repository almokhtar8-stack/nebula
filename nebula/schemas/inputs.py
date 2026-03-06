"""
Internal data schemas for Nebula MVP pipeline.
All inter-module data passes through these typed models.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class GenomeBuild(str, Enum):
    GRCH37 = "GRCh37"
    GRCH38 = "GRCh38"
    HG19 = "hg19"
    HG38 = "hg38"


class EvidenceGrade(str, Enum):
    STRONG = "Strong"
    MODERATE = "Moderate"
    EXPLORATORY = "Exploratory"


class OutputTier(str, Enum):
    """Three-tier safety classification."""
    TIER_1 = "tier_1"   # Wellness insight — no physician action needed
    TIER_2 = "tier_2"   # Risk flag — recommend physician discussion
    TIER_3 = "tier_3"   # Clinical referral — requires human review before release


class RuleCategory(str, Enum):
    FITNESS = "Fitness"
    NUTRITION = "Nutrition"
    RECOVERY_SLEEP = "Recovery/Sleep"
    HEALTH_RISK = "Health Risk"


# ---------------------------------------------------------------------------
# VCF / Variant schemas
# ---------------------------------------------------------------------------


class RawVariant(BaseModel):
    """A single variant as parsed from the VCF."""
    chrom: str
    pos: int
    rsid: str | None
    ref: str
    alt: str
    genotype: str          # e.g. "0/1", "1/1", "0/0"
    gt_alleles: list[str]  # resolved allele strings e.g. ["A", "C"]
    filter_pass: bool = True
    gq: int | None = None  # Genotype Quality
    dp: int | None = None  # Read Depth (for sequencing; may be None for arrays)


class SampleQCResult(BaseModel):
    """Outcome of per-sample QC checks."""
    sample_id: str
    genome_build: GenomeBuild
    total_variants: int
    pass_filter_variants: int
    call_rate: float                # fraction of non-missing genotypes
    call_rate_pass: bool
    het_rate: float                 # heterozygosity rate
    het_rate_pass: bool
    whitelist_coverage: float       # fraction of whitelist rsIDs found
    whitelist_coverage_pass: bool
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def overall_pass(self) -> bool:
        return self.call_rate_pass and self.whitelist_coverage_pass and len(self.errors) == 0


# ---------------------------------------------------------------------------
# Questionnaire / metadata schema
# ---------------------------------------------------------------------------


class ExerciseGoal(str, Enum):
    ENDURANCE = "endurance"
    STRENGTH = "strength"
    POWER = "power"
    FAT_LOSS = "fat_loss"
    GENERAL_WELLNESS = "general_wellness"
    SLEEP_OPTIMIZATION = "sleep_optimization"


class DietType(str, Enum):
    OMNIVORE = "omnivore"
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    KETO = "keto"
    PALEO = "paleo"
    OTHER = "other"


class SleepQuality(str, Enum):
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


class SexBio(str, Enum):
    MALE = "male"
    FEMALE = "female"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class UserMetadata(BaseModel):
    """Structured lifestyle questionnaire + demographics."""
    sample_id: str
    age: int = Field(ge=18, le=120)
    sex_biological: SexBio

    # Fitness
    exercise_goals: list[ExerciseGoal] = Field(default_factory=list)
    training_frequency_per_week: int = Field(ge=0, le=14, default=3)
    exercise_types: list[str] = Field(default_factory=list)   # e.g. ["running", "weights"]
    injury_history: bool = False

    # Nutrition
    diet_type: DietType = DietType.OMNIVORE
    caffeine_mg_per_day: int = Field(ge=0, default=100)
    alcohol_drinks_per_week: int = Field(ge=0, default=0)
    dairy_intake: bool = True
    supplement_use: list[str] = Field(default_factory=list)

    # GI / symptoms
    gi_symptoms: bool = False
    gi_symptom_types: list[str] = Field(default_factory=list)  # e.g. ["bloating", "diarrhea"]

    # Sleep
    sleep_quality: SleepQuality = SleepQuality.GOOD
    sleep_hours_per_night: float = Field(ge=0, le=24, default=7.5)
    schedule_requires_early_wake: bool = False
    persistent_insomnia: bool = False

    # Health context
    family_history_cvd: bool = False
    family_history_breast_cancer: bool = False
    family_history_diabetes: bool = False
    currently_on_statins: bool = False
    pregnancy_planning: bool = False

    # Geography / environment
    latitude_degrees: float | None = None
    sun_exposure_hours_per_day: float | None = None

    # Goals
    goals: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Whitelist / feature schemas
# ---------------------------------------------------------------------------


class WhitelistEntry(BaseModel):
    """One entry from the curated variant whitelist CSV."""
    rsid: str
    gene: str
    category: str
    trait: str
    risk_allele: str
    ref_allele: str
    evidence_grade: EvidenceGrade
    notes: str = ""


class GeneticFeature(BaseModel):
    """Resolved genetic feature for a whitelist variant in a specific sample."""
    rsid: str
    gene: str
    category: str
    trait: str
    genotype: str          # e.g. "AA", "AC", "CC"
    alleles: list[str]     # e.g. ["A", "C"]
    risk_allele: str
    risk_allele_count: int  # 0, 1, or 2
    evidence_grade: EvidenceGrade
    found_in_vcf: bool = True


class PRSScore(BaseModel):
    """A polygenic risk score computed for one condition."""
    condition: str           # e.g. "CAD"
    raw_score: float
    percentile: float        # 0-100
    reference_population: str = "European (1000G)"
    ancestry_match_flag: bool = True  # False = warn about ancestry mismatch
    note: str = ""


# ---------------------------------------------------------------------------
# Rule engine output schemas
# ---------------------------------------------------------------------------


class RuleResult(BaseModel):
    """Output of a single fired rule."""
    rule_id: str
    category: RuleCategory
    triggered: bool
    recommendation_text: str
    reason: str
    data_sources: list[str]
    evidence_grade: EvidenceGrade
    confidence_score: int = Field(ge=0, le=100)
    practical_action: str
    review_interval: str
    disclaimer: str
    referral_trigger: bool
    output_tier: OutputTier
    rule_version: str = "v0_1"
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Report schemas
# ---------------------------------------------------------------------------


class ReportSummary(BaseModel):
    sample_id: str
    report_version: str
    generated_at: str
    total_insights: int
    strong_evidence_count: int
    moderate_evidence_count: int
    exploratory_count: int
    referral_triggers: list[str]
    top_insights: list[str]


class EvidenceEntry(BaseModel):
    recommendation_id: str
    evidence_grade: EvidenceGrade
    confidence_score: int
    data_sources: list[str]


class NextStep(BaseModel):
    action: str
    reason: str
    urgency: str  # "routine" | "recommended" | "urgent"


class NebulaReport(BaseModel):
    """Top-level report structure matching the Deliverable 4 template."""
    schema_version: str = "1.0"
    report_id: str
    sample_id: str
    generated_at: str
    pipeline_version: str = "0.1.0"
    ruleset_version: str

    # Section A
    summary: ReportSummary

    # Sections C–G (merged as insights by category)
    insights: dict[str, list[RuleResult]]  # keyed by RuleCategory value

    # Section F — watchlist (Tier 2 + Tier 3)
    watchlist: list[RuleResult]

    # Section H
    evidence_confidence: list[EvidenceEntry]

    # Section I
    next_steps: list[NextStep]

    # Section J
    disclaimers: list[str]

    # QC metadata
    qc_summary: dict[str, Any]

    # PRS scores (raw, for transparency)
    prs_scores: list[PRSScore]
