"""Tests for whitelist loading and feature extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

from nebula.ingestion import parse_vcf
from nebula.whitelist import extract_features, load_whitelist, whitelist_rsids


class TestLoadWhitelist:
    def test_loads_all_entries(self, whitelist_path: Path) -> None:
        wl = load_whitelist(whitelist_path)
        assert len(wl) >= 40, "Expect at least 40 whitelist entries"

    def test_entries_have_rsids(self, whitelist_path: Path) -> None:
        wl = load_whitelist(whitelist_path)
        for entry in wl:
            assert entry.rsid.startswith("rs")

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_whitelist(tmp_path / "missing.csv")

    def test_missing_columns_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.csv"
        f.write_text("rsid,gene\nrs1,GENE1\n")
        with pytest.raises(ValueError, match="missing required columns"):
            load_whitelist(f)

    def test_whitelist_rsids_returns_set(self, whitelist_path: Path) -> None:
        wl = load_whitelist(whitelist_path)
        rsids = whitelist_rsids(wl)
        assert isinstance(rsids, set)
        assert "rs762551" in rsids  # CYP1A2


class TestExtractFeatures:
    def test_extraction_matches_vcf(self, whitelist_path: Path, sample_vcf: Path) -> None:
        wl = load_whitelist(whitelist_path)
        _, _, variants = parse_vcf(sample_vcf)
        features = extract_features(wl, variants)
        assert len(features) == len(wl)

    def test_found_features_have_genotype(self, whitelist_path: Path, sample_vcf: Path) -> None:
        wl = load_whitelist(whitelist_path)
        _, _, variants = parse_vcf(sample_vcf)
        features = extract_features(wl, variants)
        found = [f for f in features if f.found_in_vcf]
        assert len(found) > 30
        for f in found:
            assert f.genotype != ""
            assert f.risk_allele_count in (0, 1, 2)

    def test_not_found_features_marked(self, whitelist_path: Path, tmp_path: Path) -> None:
        """An empty VCF should produce all features with found_in_vcf=False."""
        vcf = tmp_path / "empty.vcf"
        vcf.write_text(
            "##fileformat=VCFv4.2\n##reference=GRCh37\n"
            "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tX\n"
        )
        _, _, variants = parse_vcf(vcf)
        wl = load_whitelist(whitelist_path)
        features = extract_features(wl, variants)
        not_found = [f for f in features if not f.found_in_vcf]
        assert len(not_found) == len(wl)

    def test_cyp1a2_slow_metabolizer_detected(
        self, whitelist_path: Path, sample_vcf: Path
    ) -> None:
        """SAMPLE_001 has rs762551 0/1 — should have 1 risk allele (C)."""
        wl = load_whitelist(whitelist_path)
        _, _, variants = parse_vcf(sample_vcf)
        features = extract_features(wl, variants)
        cyp = next(f for f in features if f.rsid == "rs762551")
        assert cyp.found_in_vcf
        assert cyp.risk_allele_count == 1  # heterozygous slow

    def test_lct_non_persistence_detected(self, whitelist_path: Path, sample_vcf: Path) -> None:
        """SAMPLE_001 has rs4988235 1/1 (TT) — lactase non-persistent."""
        wl = load_whitelist(whitelist_path)
        _, _, variants = parse_vcf(sample_vcf)
        features = extract_features(wl, variants)
        lct = next(f for f in features if f.rsid == "rs4988235")
        assert lct.found_in_vcf
        assert lct.risk_allele_count == 2  # homozygous non-persistent
