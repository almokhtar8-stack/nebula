"""
Surveillance system tests.

All network calls are mocked — these tests run fully offline.
The real API clients are tested for correct request formation
and response parsing, not live data.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nebula.surveillance.models import (
    DataSource,
    EvidenceSignal,
    GWASHit,
    PubMedPaper,
    ReviewQueue,
    ReviewStatus,
    SurveillanceCandidate,
)
from nebula.surveillance.queue import (
    approve_candidate,
    get_summary_report,
    load_queue,
    merge_candidates,
    reject_candidate,
    save_queue,
)
from nebula.surveillance.scorer import score_candidate


# ---------------------------------------------------------------------------
# Scorer tests — no network needed
# ---------------------------------------------------------------------------

class TestScorer:
    def _make_hit(
        self,
        p_value: float = 1e-10,
        sample_size: int = 100_000,
        ancestry: str = "European",
    ) -> GWASHit:
        return GWASHit(
            rsid="rs762551",
            trait="Caffeine metabolism",
            p_value=p_value,
            sample_size=sample_size,
            ancestry=ancestry,
        )

    def _make_paper(self, title: str = "A GWAS of caffeine metabolism") -> PubMedPaper:
        return PubMedPaper(
            pmid="12345678",
            title=title,
            journal="Nature Genetics",
            pub_date="2024",
        )

    def test_strong_candidate_high_n(self) -> None:
        hits = [self._make_hit() for _ in range(3)]  # 3 studies
        papers = [self._make_paper()]
        candidate = score_candidate(
            rsid="rs762551",
            trait="Caffeine metabolism",
            gene="CYP1A2",
            gwas_hits=hits,
            papers=papers,
            existing_whitelist={},
        )
        assert candidate.signal == EvidenceSignal.STRONG_CANDIDATE
        assert candidate.auto_score >= 70

    def test_weak_candidate_small_n(self) -> None:
        hits = [self._make_hit(sample_size=500)]
        candidate = score_candidate(
            rsid="rs999999",
            trait="Some trait",
            gene="GENE1",
            gwas_hits=hits,
            papers=[],
            existing_whitelist={},
        )
        assert candidate.signal in (
            EvidenceSignal.WEAK, EvidenceSignal.MODERATE_CANDIDATE
        )

    def test_contradiction_detected(self) -> None:
        from nebula.whitelist.extractor import WhitelistEntry
        from nebula.schemas import EvidenceGrade

        existing = {
            "rs762551": WhitelistEntry(
                rsid="rs762551",
                gene="CYP1A2",
                category="Caffeine",
                trait="Caffeine metabolism",
                risk_allele="C",
                ref_allele="A",
                evidence_grade=EvidenceGrade.STRONG,
            )
        }

        null_paper = self._make_paper(
            title="Caffeine metabolism variants did not replicate in African cohort"
        )

        candidate = score_candidate(
            rsid="rs762551",
            trait="Caffeine metabolism",
            gene="CYP1A2",
            gwas_hits=[self._make_hit(sample_size=80_000)],
            papers=[null_paper],
            existing_whitelist=existing,
        )
        assert candidate.contradicts_existing is True
        assert candidate.signal == EvidenceSignal.CONTRADICTS_EXISTING
        assert candidate.already_in_whitelist is True

    def test_already_in_whitelist_flagged(self) -> None:
        from nebula.whitelist.extractor import WhitelistEntry
        from nebula.schemas import EvidenceGrade

        existing = {
            "rs762551": WhitelistEntry(
                rsid="rs762551",
                gene="CYP1A2",
                category="Caffeine",
                trait="Caffeine metabolism",
                risk_allele="C",
                ref_allele="A",
                evidence_grade=EvidenceGrade.STRONG,
            )
        }
        candidate = score_candidate(
            rsid="rs762551",
            trait="Caffeine metabolism",
            gene="CYP1A2",
            gwas_hits=[self._make_hit()],
            papers=[],
            existing_whitelist=existing,
        )
        assert candidate.already_in_whitelist is True
        assert candidate.existing_evidence_grade == "Strong"

    def test_insufficient_data_no_hits(self) -> None:
        candidate = score_candidate(
            rsid="rs000000",
            trait="Unknown trait",
            gene="GENE_X",
            gwas_hits=[],
            papers=[],
            existing_whitelist={},
        )
        assert candidate.signal == EvidenceSignal.INSUFFICIENT_DATA
        assert candidate.auto_score == 0

    def test_score_bounds(self) -> None:
        hits = [self._make_hit() for _ in range(10)]
        candidate = score_candidate(
            rsid="rs762551",
            trait="test",
            gene="GENE",
            gwas_hits=hits,
            papers=[self._make_paper() for _ in range(5)],
            existing_whitelist={},
        )
        assert 0 <= candidate.auto_score <= 100

    def test_multi_ancestry_bonus(self) -> None:
        hits = [
            self._make_hit(ancestry="European"),
            self._make_hit(ancestry="East Asian"),
            self._make_hit(ancestry="African"),
        ]
        candidate = score_candidate(
            rsid="rs762551",
            trait="test",
            gene="GENE",
            gwas_hits=hits,
            papers=[],
            existing_whitelist={},
        )
        reasons_text = " ".join(candidate.score_reasons).lower()
        assert "multi-ancestry" in reasons_text or "ancestry" in reasons_text


# ---------------------------------------------------------------------------
# Queue tests — no network needed
# ---------------------------------------------------------------------------

class TestQueue:
    def _make_candidate(
        self,
        rsid: str = "rs762551",
        signal: EvidenceSignal = EvidenceSignal.STRONG_CANDIDATE,
        candidate_id: str | None = None,
    ) -> SurveillanceCandidate:
        return SurveillanceCandidate(
            candidate_id=candidate_id or f"surv_{rsid}_abc01",
            source=DataSource.GWAS_CATALOG,
            rsid=rsid,
            trait="Test trait",
            gene="GENE1",
            signal=signal,
            auto_score=75,
        )

    def test_save_and_load_queue(self, tmp_path: Path) -> None:
        queue = ReviewQueue()
        queue.candidates.append(self._make_candidate())
        path = tmp_path / "queue.json"
        save_queue(queue, path)
        loaded = load_queue(path)
        assert len(loaded.candidates) == 1
        assert loaded.candidates[0].rsid == "rs762551"

    def test_load_missing_queue_returns_empty(self, tmp_path: Path) -> None:
        q = load_queue(tmp_path / "nonexistent.json")
        assert len(q.candidates) == 0

    def test_merge_adds_new_candidates(self) -> None:
        queue = ReviewQueue()
        c1 = self._make_candidate("rs762551", candidate_id="cand_001")
        c2 = self._make_candidate("rs4988235", candidate_id="cand_002")
        added, updated = merge_candidates(queue, [c1, c2])
        assert added == 2
        assert updated == 0
        assert len(queue.candidates) == 2

    def test_merge_skips_already_reviewed(self) -> None:
        queue = ReviewQueue()
        c = self._make_candidate(candidate_id="cand_001")
        c.review_status = ReviewStatus.APPROVED
        queue.candidates.append(c)

        # Same candidate_id, still approved — should be skipped
        new_c = self._make_candidate(candidate_id="cand_001")
        added, updated = merge_candidates(queue, [new_c])
        assert added == 0
        assert updated == 0

    def test_merge_always_updates_contradictions(self) -> None:
        queue = ReviewQueue()
        c = self._make_candidate(
            candidate_id="cand_001",
            signal=EvidenceSignal.CONTRADICTS_EXISTING,
        )
        c.review_status = ReviewStatus.APPROVED
        c.contradicts_existing = True
        queue.candidates.append(c)

        new_c = self._make_candidate(
            candidate_id="cand_001",
            signal=EvidenceSignal.CONTRADICTS_EXISTING,
        )
        new_c.contradicts_existing = True
        added, updated = merge_candidates(queue, [new_c])
        # Contradictions always get updated even if previously reviewed
        assert updated == 1
        assert queue.candidates[0].review_status == ReviewStatus.PENDING

    def test_approve_candidate(self) -> None:
        queue = ReviewQueue()
        queue.candidates.append(self._make_candidate(candidate_id="cand_001"))
        result = approve_candidate(queue, "cand_001", reviewer="dr_smith", notes="Confirmed")
        assert result is True
        assert queue.candidates[0].review_status == ReviewStatus.APPROVED
        assert queue.candidates[0].reviewed_by == "dr_smith"

    def test_reject_candidate(self) -> None:
        queue = ReviewQueue()
        queue.candidates.append(self._make_candidate(candidate_id="cand_001"))
        result = reject_candidate(queue, "cand_001", reviewer="dr_smith", notes="Weak effect")
        assert result is True
        assert queue.candidates[0].review_status == ReviewStatus.REJECTED

    def test_approve_nonexistent_returns_false(self) -> None:
        queue = ReviewQueue()
        result = approve_candidate(queue, "does_not_exist", reviewer="x")
        assert result is False

    def test_queue_summary_counts(self) -> None:
        queue = ReviewQueue()
        c1 = self._make_candidate(candidate_id="c1")
        c2 = self._make_candidate(candidate_id="c2")
        c3 = self._make_candidate(candidate_id="c3", signal=EvidenceSignal.CONTRADICTS_EXISTING)
        c3.contradicts_existing = True
        c2.review_status = ReviewStatus.APPROVED
        queue.candidates = [c1, c2, c3]

        summary = get_summary_report(queue)
        assert summary["total_candidates"] == 3
        assert summary["pending_review"] == 2
        assert summary["approved"] == 1

    def test_pending_filter(self) -> None:
        queue = ReviewQueue()
        c1 = self._make_candidate(candidate_id="c1")
        c2 = self._make_candidate(candidate_id="c2")
        c2.review_status = ReviewStatus.REJECTED
        queue.candidates = [c1, c2]
        pending = queue.pending()
        assert len(pending) == 1
        assert pending[0].candidate_id == "c1"

    def test_queue_serialisation_roundtrip(self, tmp_path: Path) -> None:
        queue = ReviewQueue()
        c = self._make_candidate()
        c.gwas_hits = [GWASHit(rsid="rs762551", trait="test", p_value=1e-10)]
        c.pubmed_papers = [PubMedPaper(pmid="123", title="Test paper")]
        queue.candidates.append(c)
        path = tmp_path / "q.json"
        save_queue(queue, path)
        loaded = load_queue(path)
        assert loaded.candidates[0].gwas_hits[0].rsid == "rs762551"
        assert loaded.candidates[0].pubmed_papers[0].pmid == "123"


# ---------------------------------------------------------------------------
# Runner tests — mocked network
# ---------------------------------------------------------------------------

class TestRunner:
    @patch("nebula.surveillance.runner.get_associations_for_rsid")
    @patch("nebula.surveillance.runner.search_rsid")
    @patch("nebula.surveillance.runner.fetch_papers")
    def test_dry_run_does_not_write_queue(
        self,
        mock_fetch: MagicMock,
        mock_search: MagicMock,
        mock_gwas: MagicMock,
        tmp_path: Path,
        whitelist_path: Path,
    ) -> None:
        mock_search.return_value = ["12345678"]
        mock_fetch.return_value = [
            PubMedPaper(pmid="12345678", title="Test GWAS", journal="Nat Genet", pub_date="2024")
        ]
        mock_gwas.return_value = [
            GWASHit(rsid="rs762551", trait="Caffeine", p_value=1e-12, sample_size=120_000)
        ]

        queue_path = tmp_path / "queue.json"

        from nebula.surveillance.runner import run_surveillance
        run = run_surveillance(
            whitelist_path=whitelist_path,
            queue_path=queue_path,
            config={},
            dry_run=True,
        )

        assert not queue_path.exists(), "Dry run should not write queue file"
        assert run.rsids_checked > 0

    @patch("nebula.surveillance.runner.get_associations_for_rsid")
    @patch("nebula.surveillance.runner.search_rsid")
    @patch("nebula.surveillance.runner.fetch_papers")
    def test_run_saves_strong_candidates(
        self,
        mock_fetch: MagicMock,
        mock_search: MagicMock,
        mock_gwas: MagicMock,
        tmp_path: Path,
        whitelist_path: Path,
    ) -> None:
        # Return strong evidence for every rsID
        mock_search.return_value = ["12345678"]
        mock_fetch.return_value = [
            PubMedPaper(pmid="12345678", title="Large GWAS replication", pub_date="2024")
        ]
        mock_gwas.return_value = [
            GWASHit(
                rsid="rs762551", trait="Caffeine metabolism",
                p_value=1e-15, sample_size=200_000, ancestry="European"
            ),
            GWASHit(
                rsid="rs762551", trait="Caffeine metabolism",
                p_value=2e-12, sample_size=50_000, ancestry="East Asian"
            ),
        ]

        queue_path = tmp_path / "queue.json"
        from nebula.surveillance.runner import run_surveillance
        run = run_surveillance(
            whitelist_path=whitelist_path,
            queue_path=queue_path,
            config={},
            dry_run=False,
        )

        assert queue_path.exists()
        queue = load_queue(queue_path)
        assert len(queue.candidates) > 0
        assert run.candidates_generated > 0
