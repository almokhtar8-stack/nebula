"""Tests for VCF ingestion and metadata loading."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from nebula.ingestion import load_metadata, parse_vcf, run_qc
from nebula.schemas import GenomeBuild


class TestParseVcf:
    def test_parses_synthetic_sample(self, sample_vcf: Path, tmp_path: Path) -> None:
        sample_id, genome_build, variants = parse_vcf(sample_vcf)
        assert sample_id == "SAMPLE_001"
        assert genome_build == GenomeBuild.GRCH37
        assert len(variants) > 40

    def test_detects_genome_build_grch38(self, tmp_path: Path) -> None:
        vcf = tmp_path / "test.vcf"
        vcf.write_text(
            textwrap.dedent("""\
                ##fileformat=VCFv4.2
                ##reference=GRCh38
                #CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE_X
                1\t1000\trs123\tA\tC\t99\tPASS\t.\tGT\t0/1
            """)
        )
        _, build, _ = parse_vcf(vcf)
        assert build == GenomeBuild.GRCH38

    def test_missing_chrom_line_raises(self, tmp_path: Path) -> None:
        vcf = tmp_path / "bad.vcf"
        vcf.write_text("##fileformat=VCFv4.2\n1\t1000\trs1\tA\tC\t.\t.\t.\tGT\t0/1\n")
        with pytest.raises(ValueError, match="sample ID"):
            parse_vcf(vcf)

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            parse_vcf(tmp_path / "nonexistent.vcf")

    def test_missing_genotype_handled(self, tmp_path: Path) -> None:
        vcf = tmp_path / "missing_gt.vcf"
        vcf.write_text(
            textwrap.dedent("""\
                ##fileformat=VCFv4.2
                ##reference=GRCh37
                #CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE_X
                1\t1000\trs762551\tA\tC\t99\tPASS\t.\tGT:GQ\t./.:20
            """)
        )
        _, _, variants = parse_vcf(vcf)
        assert len(variants) == 1
        assert variants[0].genotype == "missing"

    def test_pass_filter_set_correctly(self, tmp_path: Path) -> None:
        vcf = tmp_path / "filter.vcf"
        vcf.write_text(
            textwrap.dedent("""\
                ##fileformat=VCFv4.2
                ##reference=GRCh37
                #CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE_X
                1\t1000\trs1\tA\tC\t99\tPASS\t.\tGT\t0/1
                1\t2000\trs2\tA\tT\t10\tLowQ\t.\tGT\t0/1
            """)
        )
        _, _, variants = parse_vcf(vcf)
        assert variants[0].filter_pass is True
        assert variants[1].filter_pass is False


class TestRunQc:
    def test_passing_sample(self, sample_vcf: Path) -> None:
        sample_id, genome_build, variants = parse_vcf(sample_vcf)
        qc = run_qc(sample_id, genome_build, variants, set())
        assert qc.overall_pass is True
        assert qc.call_rate > 0.95

    def test_low_call_rate_fails(self, tmp_path: Path) -> None:
        """A VCF with mostly missing calls should fail call rate QC."""
        lines = ["##fileformat=VCFv4.2\n##reference=GRCh37\n"]
        lines.append("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tBAD_SAMP\n")
        # 50 missing genotypes
        for i in range(50):
            lines.append(f"1\t{1000+i}\trs{i}\tA\tC\t99\tPASS\t.\tGT\t./.\n")
        # 1 valid
        lines.append("1\t99999\trs99\tA\tC\t99\tPASS\t.\tGT\t0/1\n")

        vcf = tmp_path / "low_cr.vcf"
        vcf.write_text("".join(lines))
        _, build, variants = parse_vcf(vcf)
        from nebula.schemas import GenomeBuild
        qc = run_qc("BAD_SAMP", GenomeBuild.GRCH37, variants, set())
        assert qc.call_rate_pass is False
        assert not qc.overall_pass

    def test_whitelist_coverage_computed(self, sample_vcf: Path) -> None:
        from nebula.whitelist import load_whitelist, whitelist_rsids
        from tests.conftest import WHITELIST_PATH
        wl = load_whitelist(WHITELIST_PATH)
        rsids = whitelist_rsids(wl)
        sample_id, genome_build, variants = parse_vcf(sample_vcf)
        qc = run_qc(sample_id, genome_build, variants, rsids)
        assert qc.whitelist_coverage > 0.0


class TestLoadMetadata:
    def test_loads_sample_001(self, sample_meta: Path) -> None:
        meta = load_metadata(sample_meta)
        assert meta.sample_id == "SAMPLE_001"
        assert meta.age == 34
        assert meta.sex_biological.value == "female"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_metadata(tmp_path / "no.json")

    def test_bad_json_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("{this is not json}")
        with pytest.raises(ValueError, match="malformed"):
            load_metadata(f)

    def test_invalid_age_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "invalid.json"
        f.write_text(json.dumps({"sample_id": "X", "age": 10, "sex_biological": "male"}))
        with pytest.raises(ValueError):
            load_metadata(f)
