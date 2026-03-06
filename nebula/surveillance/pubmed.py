"""
PubMed E-utilities API client.

Uses NCBI's free public API — no authentication required for basic use.
Rate limit: 3 requests/second without API key, 10/second with one.
We stay well under this with built-in delays.

Docs: https://www.ncbi.nlm.nih.gov/books/NBK25499/
"""

from __future__ import annotations

import logging
import time
import urllib.parse
import urllib.request
import urllib.error
import json
from typing import Any

from nebula.surveillance.models import PubMedPaper

logger = logging.getLogger(__name__)

PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
REQUEST_DELAY = 0.4   # seconds between requests — stays under rate limit
MAX_RESULTS_PER_QUERY = 20


def _get(url: str, retries: int = 3) -> dict[str, Any]:
    """HTTP GET with retry logic and rate limiting."""
    for attempt in range(retries):
        try:
            time.sleep(REQUEST_DELAY)
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Nebula-Surveillance/0.1 (research; contact@nebula.bio)"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                wait = 2 ** attempt
                logger.warning("PubMed rate limit hit — waiting %ds", wait)
                time.sleep(wait)
            else:
                logger.error("PubMed HTTP error %d for %s", exc.code, url)
                raise
        except Exception as exc:
            if attempt == retries - 1:
                raise
            logger.warning("PubMed request failed (attempt %d): %s", attempt + 1, exc)
            time.sleep(1)
    return {}


def search_rsid(
    rsid: str,
    trait_hint: str = "",
    since_date: str | None = None,
    max_results: int = MAX_RESULTS_PER_QUERY,
    api_key: str | None = None,
) -> list[str]:
    """
    Search PubMed for papers mentioning an rsID.

    Args:
        rsid: e.g. "rs762551"
        trait_hint: adds to query e.g. "caffeine" — improves relevance
        since_date: ISO date string "YYYY/MM/DD" — only papers since this date
        max_results: cap on returned PMIDs
        api_key: optional NCBI API key for higher rate limits

    Returns:
        List of PMIDs (strings)
    """
    query_parts = [rsid]
    if trait_hint:
        query_parts.append(trait_hint)
    # Focus on association / replication studies
    query_parts.append("(GWAS OR association OR replication OR pharmacogenomics)")

    query = " AND ".join(query_parts)

    params: dict[str, str] = {
        "db": "pubmed",
        "term": query,
        "retmax": str(max_results),
        "retmode": "json",
        "sort": "relevance",
    }

    if since_date:
        params["mindate"] = since_date
        params["datetype"] = "pdat"

    if api_key:
        params["api_key"] = api_key

    url = f"{PUBMED_BASE}/esearch.fcgi?{urllib.parse.urlencode(params)}"

    try:
        data = _get(url)
        pmids: list[str] = data.get("esearchresult", {}).get("idlist", [])
        logger.info("PubMed search '%s' → %d PMIDs", rsid, len(pmids))
        return pmids
    except Exception as exc:
        logger.error("PubMed search failed for %s: %s", rsid, exc)
        return []


def fetch_papers(pmids: list[str], api_key: str | None = None) -> list[PubMedPaper]:
    """
    Fetch full paper metadata for a list of PMIDs.

    Returns list of PubMedPaper objects.
    """
    if not pmids:
        return []

    params: dict[str, str] = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "json",
        "rettype": "abstract",
    }
    if api_key:
        params["api_key"] = api_key

    url = f"{PUBMED_BASE}/efetch.fcgi?{urllib.parse.urlencode(params)}"

    # efetch returns XML by default — use summary endpoint for JSON
    summary_url = (
        f"{PUBMED_BASE}/esummary.fcgi?"
        f"{urllib.parse.urlencode({**params, 'rettype': 'docsum'})}"
    )

    try:
        data = _get(summary_url)
    except Exception as exc:
        logger.error("PubMed fetch failed for PMIDs %s: %s", pmids[:3], exc)
        return []

    results = data.get("result", {})
    papers: list[PubMedPaper] = []

    for pmid in pmids:
        entry = results.get(pmid, {})
        if not entry or "error" in entry:
            continue

        authors = [
            a.get("name", "") for a in entry.get("authors", [])
        ]

        # Build abstract URL (abstract not in esummary — link to PubMed)
        pub_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

        papers.append(
            PubMedPaper(
                pmid=pmid,
                title=entry.get("title", "").rstrip("."),
                abstract="",  # Not in esummary; fetched separately if needed
                authors=authors[:5],  # cap at 5
                journal=entry.get("source", ""),
                pub_date=entry.get("pubdate", ""),
                doi=next(
                    (
                        a.get("value", "")
                        for a in entry.get("articleids", [])
                        if a.get("idtype") == "doi"
                    ),
                    "",
                ),
                url=pub_url,
            )
        )

    logger.info("Fetched metadata for %d papers", len(papers))
    return papers


def fetch_abstract(pmid: str, api_key: str | None = None) -> str:
    """
    Fetch the abstract text for a single paper.
    Used selectively when AI summarisation is enabled.
    """
    params: dict[str, str] = {
        "db": "pubmed",
        "id": pmid,
        "retmode": "text",
        "rettype": "abstract",
    }
    if api_key:
        params["api_key"] = api_key

    url = f"{PUBMED_BASE}/efetch.fcgi?{urllib.parse.urlencode(params)}"

    try:
        time.sleep(REQUEST_DELAY)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Nebula-Surveillance/0.1"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8").strip()
    except Exception as exc:
        logger.error("Abstract fetch failed for PMID %s: %s", pmid, exc)
        return ""
