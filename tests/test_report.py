"""Tests for report builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nebula.engine import compute_prs, evaluate_rules, load_ruleset
from nebula.ingestion import load_metadata, parse_vcf, run_qc
from nebula.report import build_report
from nebula.schemas import OutputTier
from nebula.whitelist import extract_features, load_whitelist, whitelist_rsids


@pytest.fixture(scope="module")
def full_report(
    sample_vcf: Path,
    sample_meta: Path,
    whitelist_path: Path,
    ruleset_path: Path,
):
    wl = load_whitelist(whitelist_path)
    rsids = whitelist_rsids(wl)
    sample_id, genome_build, variants = parse_vcf(sample_vcf)
    qc = run_qc(sample_id, genome_build, variants, rsids)
    metadata = load_metadata(sample_meta)
    features = extract_features(wl, variants)
    ruleset = load_ruleset(ruleset_path)
    prs = compute_prs(features, metadata.sex_biological.value)
    results = evaluate_rules(ruleset, features, prs, metadata)
    report = build_report(
        metadata=metadata,
        qc_result=qc,
        features=features,
        prs_scores=prs,
        rule_results=results,
        ruleset_version=str(ruleset["version"]),
    )
    return report


class TestReportStructure:
    def test_report_has_all_sections(self, full_report) -> None:
        assert full_report.summary is not None
        assert full_report.insights is not None
        assert full_report.watchlist is not None
        assert full_report.evidence_confidence is not None
        assert full_report.next_steps is not None
        assert full_report.disclaimers is not None
        assert full_report.qc_summary is not None
        assert full_report.prs_scores is not None

    def test_sample_id_propagated(self, full_report) -> None:
        assert full_report.sample_id == "SAMPLE_001"
        assert full_report.summary.sample_id == "SAMPLE_001"

    def test_report_id_is_uuid(self, full_report) -> None:
        import uuid
        uuid.UUID(full_report.report_id)  # raises if invalid

    def test_disclaimers_non_empty(self, full_report) -> None:
        assert len(full_report.disclaimers) >= 5
        for d in full_report.disclaimers:
            assert len(d) > 20

    def test_summary_counts_consistent(self, full_report) -> None:
        total = full_report.summary.total_insights
        strong = full_report.summary.strong_evidence_count
        moderate = full_report.summary.moderate_evidence_count
        exploratory = full_report.summary.exploratory_count
        assert strong + moderate + exploratory == total

    def test_watchlist_only_tier_2_3(self, full_report) -> None:
        for item in full_report.watchlist:
            assert item.output_tier in (OutputTier.TIER_2, OutputTier.TIER_3)

    def test_next_steps_non_empty(self, full_report) -> None:
        assert len(full_report.next_steps) >= 1

    def test_evidence_table_matches_insights(self, full_report) -> None:
        insight_ids = set()
        for category_results in full_report.insights.values():
            for r in category_results:
                insight_ids.add(r.rule_id)
        evidence_ids = {e.recommendation_id for e in full_report.evidence_confidence}
        assert insight_ids == evidence_ids

    def test_json_serialisable(self, full_report, tmp_path: Path) -> None:
        out = tmp_path / "report.json"
        data = full_report.model_dump()
        out.write_text(json.dumps(data, default=str))
        loaded = json.loads(out.read_text())
        assert loaded["sample_id"] == "SAMPLE_001"
        assert "summary" in loaded
        assert "insights" in loaded
        assert "disclaimers" in loaded

    def test_no_diagnosis_language(self, full_report) -> None:
        """No triggered recommendation text should contain diagnostic language."""
        forbidden = ["you have", "you are diagnosed", "you suffer from", "diagnosis of"]
        for category_results in full_report.insights.values():
            for r in category_results:
                lower = r.recommendation_text.lower()
                for phrase in forbidden:
                    assert phrase not in lower, (
                        f"Rule {r.rule_id} contains forbidden phrase '{phrase}'"
                    )

    def test_qc_summary_present(self, full_report) -> None:
        qc = full_report.qc_summary
        assert "call_rate" in qc
        assert "het_rate" in qc
        assert "whitelist_coverage" in qc
        assert qc["overall_pass"] is True
