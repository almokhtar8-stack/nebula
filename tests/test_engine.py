"""Tests for the deterministic rule engine and PRS computation."""

from __future__ import annotations

from pathlib import Path

import pytest

from nebula.engine import compute_prs, evaluate_rules, load_ruleset
from nebula.engine.rule_loader import RulesetLoadError
from nebula.ingestion import load_metadata, parse_vcf
from nebula.schemas import (
    EvidenceGrade,
    GeneticFeature,
    OutputTier,
    PRSScore,
    RuleCategory,
)
from nebula.whitelist import extract_features, load_whitelist


class TestLoadRuleset:
    def test_loads_v0_1(self, ruleset_path: Path) -> None:
        rs = load_ruleset(ruleset_path)
        assert rs["version"] == "0.1.0"
        assert len(rs["rules"]) == 21

    def test_all_rule_ids_present(self, ruleset_path: Path) -> None:
        rs = load_ruleset(ruleset_path)
        ids = {r["id"] for r in rs["rules"]}
        expected = {
            "FIT-001", "FIT-002", "FIT-003", "FIT-004",
            "NUT-001", "NUT-002", "NUT-003", "NUT-004",
            "NUT-005", "NUT-006", "NUT-007", "NUT-008",
            "REC-001", "REC-002", "REC-003",
            "RISK-001", "RISK-002", "RISK-003",
            "RISK-004", "RISK-005", "RISK-006",
        }
        assert ids == expected

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(RulesetLoadError, match="not found"):
            load_ruleset(tmp_path / "missing.yml")

    def test_missing_version_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yml"
        f.write_text("rules: []\n")
        with pytest.raises(RulesetLoadError, match="version"):
            load_ruleset(f)

    def test_duplicate_ids_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "dup.yml"
        f.write_text(
            "version: '1.0'\nrules:\n"
            "  - {id: FIT-001, category: Fitness, description: x, trigger: FIT-001,\n"
            "     recommendation_text: x, reason: x, evidence_grade: Strong,\n"
            "     base_confidence: 80, practical_action: x, review_interval: x,\n"
            "     disclaimer: x, referral_trigger: false, output_tier: tier_1}\n"
            "  - {id: FIT-001, category: Fitness, description: x, trigger: FIT-001,\n"
            "     recommendation_text: x, reason: x, evidence_grade: Strong,\n"
            "     base_confidence: 80, practical_action: x, review_interval: x,\n"
            "     disclaimer: x, referral_trigger: false, output_tier: tier_1}\n"
        )
        with pytest.raises(RulesetLoadError, match="Duplicate"):
            load_ruleset(f)


class TestEvaluateRules:
    @pytest.fixture(scope="class")
    def pipeline_outputs(
        self,
        sample_vcf: Path,
        sample_meta: Path,
        whitelist_path: Path,
        ruleset_path: Path,
    ):
        wl = load_whitelist(whitelist_path)
        _, _, variants = parse_vcf(sample_vcf)
        features = extract_features(wl, variants)
        metadata = load_metadata(sample_meta)
        ruleset = load_ruleset(ruleset_path)
        prs = compute_prs(features, metadata.sex_biological.value)
        results = evaluate_rules(ruleset, features, prs, metadata)
        return results, prs, metadata

    def test_rules_fire_for_sample_001(self, pipeline_outputs) -> None:
        results, _, _ = pipeline_outputs
        assert len(results) >= 5, "Expect at least 5 rules to trigger for sample 001"

    def test_nut_001_fires(self, pipeline_outputs) -> None:
        """SAMPLE_001 has CYP1A2 0/1 and poor sleep → NUT-001 should fire."""
        results, _, _ = pipeline_outputs
        ids = {r.rule_id for r in results}
        assert "NUT-001" in ids

    def test_nut_002_fires(self, pipeline_outputs) -> None:
        """SAMPLE_001 has LCT 1/1 (TT) → NUT-002 should fire."""
        results, _, _ = pipeline_outputs
        ids = {r.rule_id for r in results}
        assert "NUT-002" in ids

    def test_rec_003_fires(self, pipeline_outputs) -> None:
        """SAMPLE_001 is slow CYP1A2 + caffeine 280mg + poor sleep → REC-003."""
        results, _, _ = pipeline_outputs
        ids = {r.rule_id for r in results}
        assert "REC-003" in ids

    def test_no_rule_fires_without_trigger(self) -> None:
        """An RR ACTN3 user with endurance goals should NOT trigger FIT-002."""
        feat = GeneticFeature(
            rsid="rs1815739",
            gene="ACTN3",
            category="Fitness",
            trait="Muscle fiber type",
            genotype="TT",
            alleles=["T", "T"],
            risk_allele="C",
            risk_allele_count=0,
            evidence_grade=EvidenceGrade.STRONG,
            found_in_vcf=True,
        )
        from nebula.schemas import ExerciseGoal, SexBio, UserMetadata, DietType, SleepQuality
        meta = UserMetadata(
            sample_id="X",
            age=30,
            sex_biological=SexBio.MALE,
            exercise_goals=[ExerciseGoal.ENDURANCE],  # endurance, not strength
        )
        from nebula.engine.evaluator import TRIGGER_CONDITIONS
        fn = TRIGGER_CONDITIONS["FIT-002"]
        assert fn({"rs1815739": feat}, {}, meta) is False

    def test_confidence_within_bounds(self, pipeline_outputs) -> None:
        results, _, _ = pipeline_outputs
        for r in results:
            assert 0 <= r.confidence_score <= 100

    def test_risk_rules_have_referral_trigger(self, pipeline_outputs) -> None:
        results, _, _ = pipeline_outputs
        risk_rules = [r for r in results if r.category == RuleCategory.HEALTH_RISK]
        for r in risk_rules:
            assert r.referral_trigger is True

    def test_tier_3_rule_risk_005(self, whitelist_path, ruleset_path) -> None:
        """Manually inject a DPYD carrier and verify RISK-005 fires as tier_3."""
        import textwrap
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            vcf_path = Path(tmp) / "dpyd.vcf"
            vcf_path.write_text(
                textwrap.dedent("""\
                    ##fileformat=VCFv4.2
                    ##reference=GRCh37
                    #CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE_DPYD
                    1\t97915614\trs3918290\tG\tA\t99\tPASS\t.\tGT\t0/1
                """)
            )
            meta_path = Path(tmp) / "meta.json"
            import json
            meta_path.write_text(json.dumps({
                "sample_id": "SAMPLE_DPYD",
                "age": 45,
                "sex_biological": "male",
            }))

            wl = load_whitelist(whitelist_path)
            _, _, variants = parse_vcf(vcf_path)
            features = extract_features(wl, variants)
            metadata = load_metadata(meta_path)
            ruleset = load_ruleset(ruleset_path)
            prs = compute_prs(features, "male")
            results = evaluate_rules(ruleset, features, prs, metadata)

            risk_005 = next((r for r in results if r.rule_id == "RISK-005"), None)
            assert risk_005 is not None
            assert risk_005.output_tier == OutputTier.TIER_3
            assert risk_005.referral_trigger is True


class TestComputePrs:
    def test_returns_cad_and_t2d(
        self, whitelist_path: Path, sample_vcf: Path
    ) -> None:
        wl = load_whitelist(whitelist_path)
        _, _, variants = parse_vcf(sample_vcf)
        features = extract_features(wl, variants)
        prs = compute_prs(features, "female")
        conditions = {p.condition for p in prs}
        assert "CAD" in conditions
        assert "T2D" in conditions
        assert "BrCa" in conditions

    def test_male_returns_prostate_cancer(
        self, whitelist_path: Path, sample_vcf: Path
    ) -> None:
        wl = load_whitelist(whitelist_path)
        _, _, variants = parse_vcf(sample_vcf)
        features = extract_features(wl, variants)
        prs = compute_prs(features, "male")
        conditions = {p.condition for p in prs}
        assert "PrCa" in conditions
        assert "BrCa" not in conditions

    def test_percentiles_in_range(
        self, whitelist_path: Path, sample_vcf: Path
    ) -> None:
        wl = load_whitelist(whitelist_path)
        _, _, variants = parse_vcf(sample_vcf)
        features = extract_features(wl, variants)
        prs = compute_prs(features, "female")
        for p in prs:
            assert 0.0 <= p.percentile <= 100.0
