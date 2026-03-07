"""
Data models for the literature surveillance system.

These are separate from the main pipeline schemas because surveillance
produces candidates — not confirmed whitelist entries. Nothing here
enters the product without human approval.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EvidenceSignal(str, Enum):
    """Automated evidence signal — NOT a final classification."""
    STRONG_CANDIDATE = "strong_candidate"      # meets all criteria → flag for review
    MODERATE_CANDIDATE = "moderate_candidate"  # meets most criteria → watch list
    CONTRADICTS_EXISTING = "contradicts"       # new evidence conflicts with current entry
    WEAK = "weak"                              # logged but not flagged
    INSUFFICIENT_DATA = "insufficient_data"   # not enough info to score


class ReviewStatus(str, Enum):
    PENDING = "pending"           # awaiting human review
    APPROVED = "approved"         # genetic counselor approved for whitelist
    REJECTED = "rejected"         # reviewed and excluded
    NEEDS_COUNSELOR = "needs_counselor"  # flagged for specialist review
    WATCHING = "watching"         # watch for more evidence


class DataSource(str, Enum):
    PUBMED = "pubmed"
    GWAS_CATALOG = "gwas_catalog"
    PGS_CATALOG = "pgs_catalog"


# ---------------------------------------------------------------------------
# Raw API results
# ---------------------------------------------------------------------------

class PubMedPaper(BaseModel):
    """A single paper retrieved from PubMed."""
    pmid: str
    title: str
    abstract: str = ""
    authors: list[str] = Field(default_factory=list)
    journal: str = ""
    pub_date: str = ""
    doi: str = ""
    url: str = ""


class GWASHit(BaseModel):
    """A single association from GWAS Catalog."""
    accession: str = ""
    rsid: str
    trait: str
    trait_efo: str = ""           # EFO ontology term
    p_value: float
    beta_or_or: float | None = None
    effect_allele: str = ""
    other_allele: str = ""
    sample_size: int = 0
    ancestry: str = ""
    mapped_gene: str = ""
    study_pmid: str = ""
    pub_date: str = ""


class PGSModel(BaseModel):
    """A polygenic score model from PGS Catalog."""
    pgs_id: str
    name: str
    condition: str
    trait_efo: str = ""
    num_variants: int = 0
    development_ancestry: str = ""
    pub_pmid: str = ""
    c_statistic: float | None = None
    notes: str = ""


# ---------------------------------------------------------------------------
# AI summarisation result
# ---------------------------------------------------------------------------

class PaperSummary(BaseModel):
    """Structured summary produced by Claude API for a PubMed paper."""
    pmid: str
    rsid_mentioned: str = ""
    trait: str = ""
    sample_size: int | None = None
    population: str = ""
    p_value_reported: str = ""
    effect_size_reported: str = ""
    replication_status: str = ""   # "replicated" | "novel" | "contradicts" | "null"
    three_sentence_summary: str = ""
    supports_existing: bool | None = None
    confidence_in_summary: str = "low"  # "low" | "medium" | "high"
    raw_response: str = ""


# ---------------------------------------------------------------------------
# Surveillance candidate — the core unit of the review queue
# ---------------------------------------------------------------------------

class SurveillanceCandidate(BaseModel):
    """
    A candidate variant or PRS model that has been found by surveillance
    and is awaiting human review.

    Nothing in this model is in the product. It is a proposal only.
    """
    candidate_id: str                    # deterministic: source_rsid_pmid
    source: DataSource
    rsid: str
    trait: str
    gene: str = ""

    # Evidence signals
    signal: EvidenceSignal
    auto_score: int = Field(ge=0, le=100)  # automated score — NOT confidence score
    score_reasons: list[str] = Field(default_factory=list)

    # Raw data
    gwas_hits: list[GWASHit] = Field(default_factory=list)
    pubmed_papers: list[PubMedPaper] = Field(default_factory=list)
    ai_summary: PaperSummary | None = None

    # Context
    already_in_whitelist: bool = False
    existing_evidence_grade: str | None = None  # current grade if already whitelisted
    contradicts_existing: bool = False

    # Timestamps
    found_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Review
    review_status: ReviewStatus = ReviewStatus.PENDING
    reviewer_notes: str = ""
    reviewed_at: str | None = None
    reviewed_by: str | None = None


# ---------------------------------------------------------------------------
# Surveillance run record
# ---------------------------------------------------------------------------

class SurveillanceRun(BaseModel):
    """Metadata about a single surveillance run."""
    run_id: str
    started_at: str
    completed_at: str | None = None
    whitelist_version: str = ""
    rsids_checked: int = 0
    papers_found: int = 0
    gwas_hits_found: int = 0
    candidates_generated: int = 0
    strong_candidates: int = 0
    contradictions_found: int = 0
    errors: list[str] = Field(default_factory=list)
    config_snapshot: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Review queue (persisted to disk as JSON)
# ---------------------------------------------------------------------------

class ReviewQueue(BaseModel):
    """The full pending review queue, persisted between runs."""
    schema_version: str = "1.0"
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    candidates: list[SurveillanceCandidate] = Field(default_factory=list)
    run_history: list[SurveillanceRun] = Field(default_factory=list)

    def pending(self) -> list[SurveillanceCandidate]:
        return [c for c in self.candidates if c.review_status == ReviewStatus.PENDING]

    def strong_pending(self) -> list[SurveillanceCandidate]:
        return [
            c for c in self.pending()
            if c.signal == EvidenceSignal.STRONG_CANDIDATE
        ]

    def contradictions(self) -> list[SurveillanceCandidate]:
        return [c for c in self.candidates if c.contradicts_existing]
