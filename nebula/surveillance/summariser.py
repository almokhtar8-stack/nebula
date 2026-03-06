"""
AI summarisation layer using Claude API.

This is the ONE place in Nebula where an LLM is used — and it is
explicitly NOT making health decisions. It is summarising scientific
papers to save a genetic counselor's reading time.

The human still makes every decision. The AI saves them 20 minutes
per paper.

Design principles:
- Structured JSON output only — no free-text health claims
- The summary is advisory to the reviewer, not shown to users
- Errors degrade gracefully — a failed summary is logged, not fatal
- The LLM cannot add or remove whitelist entries — only humans can
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from typing import Any

from nebula.surveillance.models import PaperSummary

logger = logging.getLogger(__name__)

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 800

SUMMARISE_PROMPT = """\
You are a scientific literature analyst for a genomics research team.
Analyse this scientific paper and extract structured information.

Respond ONLY with a JSON object — no preamble, no markdown, no explanation.

Required JSON fields:
{{
  "rsid_mentioned": "the primary rsID discussed (e.g. rs762551) or empty string",
  "trait": "the primary trait or phenotype studied (e.g. caffeine metabolism)",
  "sample_size": integer or null,
  "population": "ancestry/population studied (e.g. European, multi-ancestry)",
  "p_value_reported": "exact p-value string as reported (e.g. 3.2e-9) or empty string",
  "effect_size_reported": "beta or OR as reported (e.g. OR=1.23) or empty string",
  "replication_status": "one of: replicated | novel | contradicts | null | unclear",
  "three_sentence_summary": "exactly 3 sentences summarising the key finding, methodology, and implication for a whitelist decision",
  "supports_existing": true if this supports existing evidence, false if it contradicts, null if unclear,
  "confidence_in_summary": "one of: low | medium | high — your confidence this summary is accurate"
}}

Paper to analyse:
Title: {title}
Journal: {journal}
Date: {pub_date}
Abstract: {abstract}
"""


def summarise_paper(
    paper_title: str,
    abstract: str,
    journal: str,
    pub_date: str,
    pmid: str,
) -> PaperSummary:
    """
    Use Claude API to produce a structured summary of a paper.

    Returns a PaperSummary. On any error, returns a minimal summary
    with confidence_in_summary="low" rather than crashing.

    NOTE: Requires ANTHROPIC_API_KEY in the environment.
    """
    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping AI summarisation for %s", pmid)
        return PaperSummary(
            pmid=pmid,
            three_sentence_summary="AI summarisation skipped — API key not configured.",
            confidence_in_summary="low",
        )

    prompt = SUMMARISE_PROMPT.format(
        title=paper_title[:500],
        journal=journal,
        pub_date=pub_date,
        abstract=abstract[:3000] if abstract else "Abstract not available.",
    )

    payload = json.dumps({
        "model": CLAUDE_MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        CLAUDE_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data: dict[str, Any] = json.loads(resp.read().decode("utf-8"))

        raw_text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                raw_text += block.get("text", "")

        # Strip any accidental markdown fences
        raw_text = raw_text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        raw_text = raw_text.strip().rstrip("```")

        parsed = json.loads(raw_text)

        return PaperSummary(
            pmid=pmid,
            rsid_mentioned=parsed.get("rsid_mentioned", ""),
            trait=parsed.get("trait", ""),
            sample_size=parsed.get("sample_size"),
            population=parsed.get("population", ""),
            p_value_reported=str(parsed.get("p_value_reported", "")),
            effect_size_reported=str(parsed.get("effect_size_reported", "")),
            replication_status=parsed.get("replication_status", "unclear"),
            three_sentence_summary=parsed.get("three_sentence_summary", ""),
            supports_existing=parsed.get("supports_existing"),
            confidence_in_summary=parsed.get("confidence_in_summary", "low"),
            raw_response=raw_text[:500],
        )

    except urllib.error.HTTPError as exc:
        logger.error("Claude API HTTP error %d for paper %s", exc.code, pmid)
    except json.JSONDecodeError as exc:
        logger.error("Could not parse Claude response for %s: %s", pmid, exc)
    except Exception as exc:
        logger.error("Summarisation failed for %s: %s", pmid, exc)

    return PaperSummary(
        pmid=pmid,
        three_sentence_summary="Summarisation failed — see logs.",
        confidence_in_summary="low",
    )


def summarise_papers_for_candidate(
    papers: list[Any],  # list[PubMedPaper]
    rsid: str,
    max_to_summarise: int = 3,
) -> list[PaperSummary]:
    """
    Summarise the top N most relevant papers for a candidate.

    Caps at max_to_summarise to control API costs.
    Papers without abstracts are skipped.
    """
    summaries: list[PaperSummary] = []

    # Prioritise papers that have abstracts
    with_abstract = [p for p in papers if p.abstract]
    without_abstract = [p for p in papers if not p.abstract]
    ordered = with_abstract[:max_to_summarise] + without_abstract

    for paper in ordered[:max_to_summarise]:
        logger.debug("Summarising PMID %s for %s", paper.pmid, rsid)
        summary = summarise_paper(
            paper_title=paper.title,
            abstract=paper.abstract,
            journal=paper.journal,
            pub_date=paper.pub_date,
            pmid=paper.pmid,
        )
        summaries.append(summary)

    return summaries
