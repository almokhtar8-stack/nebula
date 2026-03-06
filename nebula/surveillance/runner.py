"""
Surveillance runner.

Orchestrates a complete surveillance run:
1. Load whitelist to get the rsIDs we already track
2. Query PubMed for new papers per rsID
3. Query GWAS Catalog for new/updated associations
4. Query PGS Catalog for new PRS models
5. Score all findings
6. Optionally summarise with AI
7. Merge into review queue
8. Save queue + run record
9. Print human-readable summary
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nebula.surveillance.gwas_catalog import get_associations_for_rsid
from nebula.surveillance.models import (
    DataSource,
    EvidenceSignal,
    ReviewQueue,
    SurveillanceRun,
)
from nebula.surveillance.pubmed import fetch_abstract, fetch_papers, search_rsid
from nebula.surveillance.queue import (
    get_summary_report,
    load_queue,
    merge_candidates,
    save_queue,
)
from nebula.surveillance.scorer import score_candidate
from nebula.whitelist.extractor import WhitelistEntry, load_whitelist

logger = logging.getLogger(__name__)


def run_surveillance(
    whitelist_path: Path,
    queue_path: Path,
    config: dict[str, Any],
    use_ai_summaries: bool = False,
    since_date: str | None = None,
    pubmed_api_key: str | None = None,
    dry_run: bool = False,
) -> SurveillanceRun:
    """
    Execute a full surveillance run.

    Args:
        whitelist_path: Path to the variant whitelist CSV
        queue_path: Path to the surveillance_queue.json file
        config: Surveillance config dict (from surveillance_config.yml)
        use_ai_summaries: Whether to call Claude API for paper summaries
        since_date: Only find papers published since this date (YYYY/MM/DD)
        pubmed_api_key: Optional NCBI API key for higher rate limits
        dry_run: If True, find and score but don't save to queue

    Returns:
        SurveillanceRun record with run statistics
    """
    run_id = str(uuid.uuid4())[:8]
    started_at = datetime.now(timezone.utc).isoformat()

    logger.info("=" * 60)
    logger.info("Nebula Surveillance Run  [%s]", run_id)
    logger.info("Started: %s", started_at)
    if since_date:
        logger.info("Searching for papers since: %s", since_date)
    logger.info("=" * 60)

    run = SurveillanceRun(
        run_id=run_id,
        started_at=started_at,
        config_snapshot=config,
    )

    # ── Load whitelist ────────────────────────────────────────────────────────
    try:
        whitelist_entries: list[WhitelistEntry] = load_whitelist(whitelist_path)
        whitelist_map: dict[str, WhitelistEntry] = {e.rsid: e for e in whitelist_entries}
        run.whitelist_version = str(whitelist_path.name)
    except Exception as exc:
        run.errors.append(f"Failed to load whitelist: {exc}")
        logger.error("Whitelist load failed: %s", exc)
        run.completed_at = datetime.now(timezone.utc).isoformat()
        return run

    run.rsids_checked = len(whitelist_entries)
    logger.info("Loaded whitelist: %d rsIDs to check", run.rsids_checked)

    # ── Load existing queue ───────────────────────────────────────────────────
    queue: ReviewQueue = load_queue(queue_path)

    # ── Per-rsID surveillance ─────────────────────────────────────────────────
    all_candidates = []
    thresholds = config.get("thresholds", {})

    for entry in whitelist_entries:
        rsid = entry.rsid
        trait_hint = entry.trait
        logger.info("Checking %s (%s — %s)...", rsid, entry.gene, entry.trait)

        # PubMed search
        papers = []
        try:
            pmids = search_rsid(
                rsid,
                trait_hint=trait_hint,
                since_date=since_date,
                api_key=pubmed_api_key,
            )
            run.papers_found += len(pmids)

            if pmids:
                papers = fetch_papers(pmids[:10], api_key=pubmed_api_key)

                # Fetch abstracts for top 3 if AI summaries are enabled
                if use_ai_summaries and papers:
                    from nebula.surveillance.summariser import fetch_abstract as fa
                    for paper in papers[:3]:
                        if not paper.abstract:
                            paper.abstract = fetch_abstract(
                                paper.pmid, api_key=pubmed_api_key
                            )

        except Exception as exc:
            logger.warning("PubMed search failed for %s: %s", rsid, exc)
            run.errors.append(f"PubMed error for {rsid}: {exc}")

        # GWAS Catalog
        gwas_hits = []
        try:
            gwas_hits = get_associations_for_rsid(rsid)
            run.gwas_hits_found += len(gwas_hits)
        except Exception as exc:
            logger.warning("GWAS Catalog failed for %s: %s", rsid, exc)
            run.errors.append(f"GWAS Catalog error for {rsid}: {exc}")

        # Score
        candidate = score_candidate(
            rsid=rsid,
            trait=trait_hint,
            gene=entry.gene,
            gwas_hits=gwas_hits,
            papers=papers,
            existing_whitelist=whitelist_map,
            thresholds=thresholds,
            candidate_id=f"surv_{rsid}_{run_id}",
        )

        # AI summary (only for strong candidates or contradictions — save costs)
        if use_ai_summaries and candidate.signal in (
            EvidenceSignal.STRONG_CANDIDATE,
            EvidenceSignal.CONTRADICTS_EXISTING,
        ):
            try:
                from nebula.surveillance.summariser import summarise_papers_for_candidate
                summaries = summarise_papers_for_candidate(papers, rsid, max_to_summarise=2)
                if summaries:
                    candidate.ai_summary = summaries[0]
            except Exception as exc:
                logger.warning("AI summary failed for %s: %s", rsid, exc)

        all_candidates.append(candidate)

    # ── Filter to meaningful candidates ──────────────────────────────────────
    # Always surface strong candidates and contradictions
    # Log but don't queue weak/insufficient
    meaningful = [
        c for c in all_candidates
        if c.signal not in (EvidenceSignal.WEAK, EvidenceSignal.INSUFFICIENT_DATA)
    ]
    run.candidates_generated = len(meaningful)
    run.strong_candidates = len([
        c for c in meaningful
        if c.signal == EvidenceSignal.STRONG_CANDIDATE
    ])
    run.contradictions_found = len([
        c for c in meaningful
        if c.contradicts_existing
    ])

    logger.info(
        "Run complete: %d candidates (%d strong, %d contradictions)",
        run.candidates_generated,
        run.strong_candidates,
        run.contradictions_found,
    )

    # ── Save ─────────────────────────────────────────────────────────────────
    if not dry_run:
        added, updated = merge_candidates(queue, meaningful)
        queue.run_history.append(run)
        save_queue(queue, queue_path)

        summary = get_summary_report(queue)
        logger.info("Queue state: %s", summary)
    else:
        logger.info("DRY RUN — queue not modified")
        for c in meaningful:
            logger.info(
                "  [%s] %s — %s — score %d",
                c.signal.value, c.rsid, c.trait, c.auto_score,
            )

    run.completed_at = datetime.now(timezone.utc).isoformat()
    return run
