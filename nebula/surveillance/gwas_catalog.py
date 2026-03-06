"""
GWAS Catalog REST API client.

Free public API — no authentication needed.
Docs: https://www.ebi.ac.uk/gwas/rest/docs/api
"""

from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
import urllib.error
from typing import Any

from nebula.surveillance.models import GWASHit

logger = logging.getLogger(__name__)

GWAS_BASE = "https://www.ebi.ac.uk/gwas/rest/api"
REQUEST_DELAY = 0.5
P_VALUE_THRESHOLD = 5e-8


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
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {}
            if exc.code == 429:
                wait = 2 ** attempt
                logger.warning("GWAS Catalog rate limit — waiting %ds", wait)
                time.sleep(wait)
            else:
                logger.error("GWAS Catalog HTTP %d for %s", exc.code, url)
                if attempt == retries - 1:
                    raise
        except Exception as exc:
            if attempt == retries - 1:
                raise
            logger.warning("GWAS request failed (attempt %d): %s", attempt + 1, exc)
            time.sleep(1)
    return {}


def _parse_association(assoc: dict[str, Any]) -> GWASHit | None:
    """Parse a raw GWAS Catalog association into a GWASHit."""
    try:
        # p-value
        p_mant = assoc.get("pvalueMantissa", 1)
        p_exp = assoc.get("pvalueExponent", 0)
        p_value = float(p_mant) * (10 ** float(p_exp))

        if p_value > P_VALUE_THRESHOLD:
            return None  # below significance threshold

        # rsID — may be in loci > strongestRiskAlleles
        rsid = ""
        loci = assoc.get("loci", [])
        for locus in loci:
            for sra in locus.get("strongestRiskAlleles", []):
                raw = sra.get("riskAlleleName", "")
                if "-" in raw:
                    rsid = raw.split("-")[0]
                elif raw.startswith("rs"):
                    rsid = raw
                break
            if rsid:
                break

        if not rsid:
            return None

        # Trait
        trait_links = assoc.get("efoTraits", [])
        trait = trait_links[0].get("trait", "") if trait_links else ""
        trait_efo = trait_links[0].get("shortForm", "") if trait_links else ""

        # Effect allele / other allele
        effect_allele = ""
        other_allele = ""
        for locus in loci:
            for sra in locus.get("strongestRiskAlleles", []):
                raw = sra.get("riskAlleleName", "")
                if "-" in raw:
                    effect_allele = raw.split("-")[1]
            break

        # Beta / OR
        beta = assoc.get("betaNum")
        or_val = assoc.get("orPerCopyNum")
        effect = beta if beta is not None else or_val

        # Sample size — from study if available
        study = assoc.get("study", {})
        sample_size = 0
        for ancestry in study.get("ancestries", []):
            for sample in ancestry.get("ancestralGroups", []):
                sample_size += sample.get("numberOfIndividuals", 0)

        # Ancestry
        ancestries = []
        for anc in study.get("ancestries", []):
            for ag in anc.get("ancestralGroups", []):
                ancestries.append(ag.get("ancestralGroup", ""))
        ancestry_str = ", ".join(set(ancestries)) if ancestries else ""

        # Gene
        gene = ""
        for locus in loci:
            for gl in locus.get("authorReportedGenes", []):
                gene = gl.get("geneName", "")
                break
            break

        # PMID
        pmid = study.get("publicationInfo", {}).get("pubmedId", "")
        pub_date = study.get("publicationInfo", {}).get("publicationDate", "")

        return GWASHit(
            accession=assoc.get("accessionId", ""),
            rsid=rsid,
            trait=trait,
            trait_efo=trait_efo,
            p_value=p_value,
            beta_or_or=effect,
            effect_allele=effect_allele,
            other_allele=other_allele,
            sample_size=sample_size,
            ancestry=ancestry_str,
            mapped_gene=gene,
            study_pmid=pmid,
            pub_date=pub_date,
        )

    except Exception as exc:
        logger.debug("Failed to parse GWAS association: %s", exc)
        return None


def get_associations_for_rsid(rsid: str) -> list[GWASHit]:
    """
    Fetch all significant associations for an rsID from GWAS Catalog.

    Returns list of GWASHit objects passing p < 5e-8.
    """
    url = f"{GWAS_BASE}/singleNucleotidePolymorphisms/{rsid}/associations"
    params = "?projection=associationBySnp&size=50"

    try:
        data = _get(url + params)
    except Exception as exc:
        logger.error("GWAS Catalog query failed for %s: %s", rsid, exc)
        return []

    embedded = data.get("_embedded", {})
    associations = embedded.get("associations", [])

    hits: list[GWASHit] = []
    for assoc in associations:
        hit = _parse_association(assoc)
        if hit and hit.rsid == rsid:
            hits.append(hit)

    logger.info("GWAS Catalog: %d significant associations for %s", len(hits), rsid)
    return hits


def search_trait_variants(
    trait_query: str,
    min_sample_size: int = 10_000,
    max_results: int = 50,
) -> list[GWASHit]:
    """
    Search GWAS Catalog for new variants associated with a trait.

    Useful for discovering variants NOT yet in your whitelist.
    """
    encoded = urllib.parse.quote(trait_query)
    url = (
        f"{GWAS_BASE}/associations/search/findByEfoTrait"
        f"?efoTrait={encoded}&size={max_results}"
    )

    try:
        data = _get(url)
    except Exception as exc:
        logger.error("GWAS trait search failed for '%s': %s", trait_query, exc)
        return []

    embedded = data.get("_embedded", {})
    associations = embedded.get("associations", [])

    hits: list[GWASHit] = []
    for assoc in associations:
        hit = _parse_association(assoc)
        if hit and (min_sample_size == 0 or hit.sample_size >= min_sample_size):
            hits.append(hit)

    logger.info(
        "GWAS trait search '%s' → %d hits (n≥%d)",
        trait_query, len(hits), min_sample_size,
    )
    return hits


def count_replications(rsid: str) -> int:
    """
    Count how many independent studies have reported this rsID in GWAS Catalog.
    Used as a proxy for replication confidence.
    """
    url = f"{GWAS_BASE}/singleNucleotidePolymorphisms/{rsid}/studies"
    try:
        data = _get(url)
        studies = data.get("_embedded", {}).get("studies", [])
        return len(studies)
    except Exception as exc:
        logger.debug("Could not count replications for %s: %s", rsid, exc)
        return 0
