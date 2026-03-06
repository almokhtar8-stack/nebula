"""
Shared pytest fixtures for Nebula test suite.
All test data is synthetic. No real genetic data is used anywhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
SYNTHETIC_DIR = DATA_DIR / "synthetic"
WHITELIST_PATH = DATA_DIR / "whitelist" / "whitelist_v0_1.csv"
RULESET_PATH = Path(__file__).parent.parent / "rulesets" / "v0_1.yml"
SAMPLE_VCF = SYNTHETIC_DIR / "sample_001.vcf"
SAMPLE_META = SYNTHETIC_DIR / "sample_001_meta.json"


@pytest.fixture(scope="session")
def whitelist_path() -> Path:
    return WHITELIST_PATH


@pytest.fixture(scope="session")
def ruleset_path() -> Path:
    return RULESET_PATH


@pytest.fixture(scope="session")
def sample_vcf() -> Path:
    return SAMPLE_VCF


@pytest.fixture(scope="session")
def sample_meta() -> Path:
    return SAMPLE_META
