"""
Review queue manager.

Persists the surveillance candidate queue to disk as JSON.
Handles merging new candidates into existing queue without
duplicating already-reviewed entries.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from nebula.surveillance.models import (
    ReviewQueue,
    ReviewStatus,
    SurveillanceCandidate,
    SurveillanceRun,
)

logger = logging.getLogger(__name__)

QUEUE_FILENAME = "surveillance_queue.json"


def load_queue(queue_path: Path) -> ReviewQueue:
    """Load existing queue from disk, or return an empty queue."""
    if not queue_path.exists():
        logger.info("No existing queue found at %s — starting fresh", queue_path)
        return ReviewQueue()

    try:
        with queue_path.open("r") as fh:
            data = json.load(fh)
        queue = ReviewQueue.model_validate(data)
        logger.info(
            "Loaded queue: %d candidates (%d pending)",
            len(queue.candidates),
            len(queue.pending()),
        )
        return queue
    except Exception as exc:
        logger.error("Failed to load queue from %s: %s — starting fresh", queue_path, exc)
        return ReviewQueue()


def save_queue(queue: ReviewQueue, queue_path: Path) -> None:
    """Save queue to disk atomically (write to .tmp then rename)."""
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue.last_updated = datetime.utcnow().isoformat()

    tmp = queue_path.with_suffix(".tmp")
    try:
        with tmp.open("w") as fh:
            json.dump(queue.model_dump(), fh, indent=2, default=str)
        tmp.rename(queue_path)
        logger.info("Saved queue to %s (%d candidates)", queue_path, len(queue.candidates))
    except Exception as exc:
        logger.error("Failed to save queue: %s", exc)
        if tmp.exists():
            tmp.unlink()
        raise


def merge_candidates(
    queue: ReviewQueue,
    new_candidates: list[SurveillanceCandidate],
) -> tuple[int, int]:
    """
    Merge new candidates into the existing queue.

    Rules:
    - If candidate_id already exists AND is already reviewed → skip (don't re-open)
    - If candidate_id already exists AND is still pending → update with fresh data
    - If candidate_id is new → append
    - Contradictions always update regardless of status (new evidence matters)

    Returns: (added_count, updated_count)
    """
    existing_map = {c.candidate_id: i for i, c in enumerate(queue.candidates)}
    added = 0
    updated = 0

    for candidate in new_candidates:
        existing_idx = existing_map.get(candidate.candidate_id)

        if existing_idx is not None:
            existing = queue.candidates[existing_idx]

            # Always update contradictions — new evidence is urgent
            if candidate.contradicts_existing:
                queue.candidates[existing_idx] = candidate
                queue.candidates[existing_idx].review_status = ReviewStatus.PENDING
                updated += 1
                logger.info(
                    "Updated contradiction candidate: %s", candidate.rsid
                )

            # Update pending ones with fresh data
            elif existing.review_status == ReviewStatus.PENDING:
                queue.candidates[existing_idx] = candidate
                updated += 1

            # Skip already-reviewed, non-contradiction entries
            else:
                logger.debug(
                    "Skipping already-reviewed candidate: %s (%s)",
                    candidate.candidate_id,
                    existing.review_status.value,
                )
        else:
            queue.candidates.append(candidate)
            existing_map[candidate.candidate_id] = len(queue.candidates) - 1
            added += 1

    logger.info("Queue merge: %d added, %d updated", added, updated)
    return added, updated


def approve_candidate(
    queue: ReviewQueue,
    candidate_id: str,
    reviewer: str,
    notes: str = "",
) -> bool:
    """Mark a candidate as approved. Returns True if found."""
    for candidate in queue.candidates:
        if candidate.candidate_id == candidate_id:
            candidate.review_status = ReviewStatus.APPROVED
            candidate.reviewer_notes = notes
            candidate.reviewed_at = datetime.utcnow().isoformat()
            candidate.reviewed_by = reviewer
            return True
    return False


def reject_candidate(
    queue: ReviewQueue,
    candidate_id: str,
    reviewer: str,
    notes: str = "",
) -> bool:
    """Mark a candidate as rejected. Returns True if found."""
    for candidate in queue.candidates:
        if candidate.candidate_id == candidate_id:
            candidate.review_status = ReviewStatus.REJECTED
            candidate.reviewer_notes = notes
            candidate.reviewed_at = datetime.utcnow().isoformat()
            candidate.reviewed_by = reviewer
            return True
    return False


def get_summary_report(queue: ReviewQueue) -> dict:
    """Return a human-readable summary of the queue state."""
    from nebula.surveillance.models import EvidenceSignal

    pending = queue.pending()
    contradictions = queue.contradictions()

    return {
        "total_candidates": len(queue.candidates),
        "pending_review": len(pending),
        "strong_candidates_pending": len([
            c for c in pending
            if c.signal == EvidenceSignal.STRONG_CANDIDATE
        ]),
        "contradictions_pending": len([
            c for c in contradictions
            if c.review_status == ReviewStatus.PENDING
        ]),
        "approved": len([
            c for c in queue.candidates
            if c.review_status == ReviewStatus.APPROVED
        ]),
        "rejected": len([
            c for c in queue.candidates
            if c.review_status == ReviewStatus.REJECTED
        ]),
        "last_updated": queue.last_updated,
        "run_count": len(queue.run_history),
    }
