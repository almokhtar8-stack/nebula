"""
PGS Catalog REST API client.

Monitors for new or improved polygenic risk score models.
Free public API — no authentication needed.
Docs: https://www.pgscatalog.org/rest/
"""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from typing import Any

from nebula.surveillance.models import PGSModel

logger = logging.getLogger(__name__)

PGS_BASE = "https://www.pgscatalog.org/rest"
REQUEST_DELAY = 0.5

# Conditions we track — maps our internal name to EFO trait ID
TRACKED_CONDITIONS: dict[str, str] = {
    "CAD":  "EFO_0001645",   # coronary artery disease
    "T2D":  "EFO_0001360",   # type 2 diabetes mellitus
    "BrCa": "EFO_0000305",   # breast carcinoma
    "PrCa": "EFO_0001663",   # prostate carcinoma
}


def _get(url: str, retries: int = 3) -> dict[str, Any]:
    for attempt in range(retries):
        try:
            time.sleep(REQUEST_DELAY)
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Nebula-Surveillance/0.1",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            if attempt == retries - 1:
                logger.error("PGS Catalog request failed: %s — %s", url, exc)
                return {}
            time.sleep(1)
    return {}


def _parse_score(score: dict[str, Any], condition: str) -> PGSModel:
    """Parse a raw PGS Catalog score entry."""
    pub = score.get("publication", {}) or {}
    pmid = pub.get("PMID", "") or ""

    # C-statistic from performance metrics if available
    c_stat: float | None = None
    for pm in score.get("performance_metrics", []):
        for effect in pm.get("performance_metrics", []):
            if effect.get("effect_unit", "") in ("C-index", "AUC"):
                try:
                    c_stat = float(effect.get("estimate", 0))
                except (ValueError, TypeError):
                    pass
                break

    return PGSModel(
        pgs_id=score.get("id", ""),
        name=score.get("name", ""),
        condition=condition,
        trait_efo=TRACKED_CONDITIONS.get(condition, ""),
        num_variants=score.get("variants_number", 0),
        development_ancestry=score.get("ancestry_distribution", {})
        .get("gwas", {})
        .get("categories", {})
        .get("European", "unknown")
        if isinstance(score.get("ancestry_distribution"), dict)
        else "unknown",
        pub_pmid=str(pmid),
        c_statistic=c_stat,
        notes=score.get("license", ""),
    )


def get_scores_for_condition(condition: str) -> list[PGSModel]:
    """
    Fetch all PGS models for a tracked condition.

    Args:
        condition: one of "CAD", "T2D", "BrCa", "PrCa"

    Returns:
        List of PGSModel objects, sorted by number of variants (proxy for
        model comprehensiveness) descending.
    """
    efo = TRACKED_CONDITIONS.get(condition)
    if not efo:
        logger.warning("Unknown condition: %s", condition)
        return []

    url = f"{PGS_BASE}/score/search?trait_id={efo}&limit=50"

    try:
        data = _get(url)
    except Exception as exc:
        logger.error("PGS Catalog query failed for %s: %s", condition, exc)
        return []

    results = data.get("results", [])
    models = [_parse_score(s, condition) for s in results]
    models.sort(key=lambda m: m.num_variants or 0, reverse=True)

    logger.info(
        "PGS Catalog: %d models for %s", len(models), condition
    )
    return models


def check_for_new_models(
    known_pgs_ids: set[str],
    condition: str,
) -> list[PGSModel]:
    """
    Return PGS models for a condition that are NOT in our known set.
    Used to detect newly published PRS models.
    """
    all_models = get_scores_for_condition(condition)
    new = [m for m in all_models if m.pgs_id not in known_pgs_ids]
    if new:
        logger.info(
            "Found %d new PGS models for %s: %s",
            len(new), condition, [m.pgs_id for m in new],
        )
    return new
