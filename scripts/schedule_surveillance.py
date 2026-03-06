#!/usr/bin/env python3
"""
Nebula surveillance scheduler.

Runs the literature surveillance system on a defined schedule.
Designed to be invoked by:
  - A cron job (simplest — see cron example below)
  - A cloud scheduler (AWS EventBridge, GCP Cloud Scheduler)
  - A systemd timer

This script is intentionally simple — it is a thin wrapper around
`nebula surveillance run` that adds scheduling logic, state persistence,
and notification support.

Usage:
    python scripts/schedule_surveillance.py               # run if due
    python scripts/schedule_surveillance.py --force       # run regardless of schedule
    python scripts/schedule_surveillance.py --check       # print next run times only

Cron example (weekly PubMed scan on Monday 2am):
    0 2 * * 1 cd /path/to/nebula && python scripts/schedule_surveillance.py

Environment variables:
    ANTHROPIC_API_KEY   — enables AI paper summarisation (optional)
    NCBI_API_KEY        — higher PubMed rate limits (optional, free at ncbi.nlm.nih.gov)
    NEBULA_NOTIFY_EMAIL — email address for run notifications (optional)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import smtplib
import sys
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from pathlib import Path

# Add project root to path if running directly
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("out/surveillance.log", mode="a"),
    ],
)
logger = logging.getLogger("nebula.scheduler")

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
WHITELIST_PATH = PROJECT_ROOT / "data" / "whitelist" / "whitelist_v0_1.csv"
CONFIG_PATH = PROJECT_ROOT / "rulesets" / "surveillance_config.yml"
QUEUE_PATH = PROJECT_ROOT / "out" / "surveillance_queue.json"
STATE_PATH = PROJECT_ROOT / "out" / "surveillance_state.json"


def load_state() -> dict:
    """Load scheduler state (last run timestamps)."""
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"last_pubmed_run": None, "last_gwas_run": None, "last_pgs_run": None}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def is_due(last_run_iso: str | None, interval_days: int) -> bool:
    """Return True if we are past the interval since the last run."""
    if last_run_iso is None:
        return True
    last = datetime.fromisoformat(last_run_iso)
    return datetime.now(timezone.utc) >= last + timedelta(days=interval_days)


def since_date_from_last_run(last_run_iso: str | None) -> str | None:
    """Convert last run ISO timestamp to PubMed date filter string."""
    if last_run_iso is None:
        return None
    dt = datetime.fromisoformat(last_run_iso)
    return dt.strftime("%Y/%m/%d")


def send_notification(subject: str, body: str) -> None:
    """Send email notification if configured."""
    to = os.environ.get("NEBULA_NOTIFY_EMAIL", "")
    if not to:
        logger.info("No NEBULA_NOTIFY_EMAIL set — skipping email notification")
        return

    smtp_host = os.environ.get("NEBULA_SMTP_HOST", "localhost")
    smtp_port = int(os.environ.get("NEBULA_SMTP_PORT", "25"))
    from_addr = os.environ.get("NEBULA_SMTP_FROM", "nebula@localhost")

    msg = MIMEText(body)
    msg["Subject"] = f"[Nebula Surveillance] {subject}"
    msg["From"] = from_addr
    msg["To"] = to

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as smtp:
            smtp.sendmail(from_addr, [to], msg.as_string())
        logger.info("Notification sent to %s", to)
    except Exception as exc:
        logger.warning("Failed to send notification: %s", exc)


def write_notification_file(run, summary: dict) -> None:
    """Write a human-readable notification file after each run."""
    out_path = PROJECT_ROOT / "out" / "surveillance_notification.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "═" * 60,
        "Nebula Literature Surveillance — Run Report",
        f"Run ID:      {run.run_id}",
        f"Completed:   {run.completed_at}",
        f"Whitelist:   {run.whitelist_version}",
        "═" * 60,
        "",
        "RESULTS",
        f"  rsIDs checked:      {run.rsids_checked}",
        f"  PubMed papers:      {run.papers_found}",
        f"  GWAS hits:          {run.gwas_hits_found}",
        f"  Candidates queued:  {run.candidates_generated}",
        f"  Strong candidates:  {run.strong_candidates}",
        f"  Contradictions:     {run.contradictions_found}",
        "",
        "QUEUE STATE",
        f"  Total candidates:   {summary.get('total_candidates', '?')}",
        f"  Pending review:     {summary.get('pending_review', '?')}",
        f"  Strong (pending):   {summary.get('strong_candidates_pending', '?')}",
        f"  Contradictions:     {summary.get('contradictions_pending', '?')}",
        f"  Approved:           {summary.get('approved', '?')}",
        "",
    ]

    if run.contradictions_found > 0:
        lines += [
            "⚠ ACTION REQUIRED: Contradictions found",
            "  These are existing whitelist entries where new evidence",
            "  may conflict. Review urgently:",
            "  → nebula surveillance review --signal contradicts",
            "",
        ]

    if run.strong_candidates > 0:
        lines += [
            f"★ {run.strong_candidates} strong candidate(s) awaiting review:",
            "  → nebula surveillance review --signal strong_candidate",
            "",
        ]

    if run.errors:
        lines += [f"  Errors ({len(run.errors)}):"] + [f"    - {e}" for e in run.errors[:5]]
        lines.append("")

    lines.append("To review full queue:  make review-queue")
    lines.append("═" * 60)

    out_path.write_text("\n".join(lines))
    logger.info("Notification file written to %s", out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Nebula surveillance scheduler")
    parser.add_argument("--force", action="store_true", help="Run regardless of schedule")
    parser.add_argument("--check", action="store_true", help="Print schedule status and exit")
    parser.add_argument("--ai-summaries", action="store_true",
                        help="Enable AI paper summarisation (requires ANTHROPIC_API_KEY)")
    args = parser.parse_args()

    # Load config
    if not CONFIG_PATH.exists():
        logger.error("Config not found: %s", CONFIG_PATH)
        sys.exit(1)
    with CONFIG_PATH.open() as fh:
        config = yaml.safe_load(fh)

    schedule = config.get("schedule", {})
    pubmed_interval = schedule.get("pubmed_interval_days", 7)
    gwas_interval = schedule.get("gwas_catalog_interval_days", 30)

    state = load_state()

    pubmed_due = is_due(state["last_pubmed_run"], pubmed_interval)
    gwas_due = is_due(state["last_gwas_run"], gwas_interval)

    if args.check:
        print("\nSurveillance schedule status")
        print("─" * 40)
        print(f"PubMed interval:     every {pubmed_interval} days")
        print(f"Last PubMed run:     {state['last_pubmed_run'] or 'never'}")
        print(f"PubMed due now:      {'YES' if pubmed_due else 'no'}")
        print(f"GWAS interval:       every {gwas_interval} days")
        print(f"Last GWAS run:       {state['last_gwas_run'] or 'never'}")
        print(f"GWAS due now:        {'YES' if gwas_due else 'no'}")
        print()
        return

    if not pubmed_due and not gwas_due and not args.force:
        logger.info("Surveillance not due. Next PubMed run in %d days. Use --force to override.",
                    pubmed_interval)
        return

    if not WHITELIST_PATH.exists():
        logger.error("Whitelist not found: %s", WHITELIST_PATH)
        sys.exit(1)

    now_iso = datetime.now(timezone.utc).isoformat()
    since = since_date_from_last_run(state.get("last_pubmed_run"))

    logger.info("Starting scheduled surveillance run (since=%s)", since or "all time")

    # Run surveillance
    from nebula.surveillance.runner import run_surveillance
    from nebula.surveillance.queue import load_queue, get_summary_report

    run = run_surveillance(
        whitelist_path=WHITELIST_PATH,
        queue_path=QUEUE_PATH,
        config=config,
        use_ai_summaries=args.ai_summaries and bool(os.environ.get("ANTHROPIC_API_KEY")),
        since_date=since,
        pubmed_api_key=os.environ.get("NCBI_API_KEY"),
        dry_run=False,
    )

    # Update state
    if pubmed_due or args.force:
        state["last_pubmed_run"] = now_iso
    if gwas_due or args.force:
        state["last_gwas_run"] = now_iso
    save_state(state)

    # Notification
    queue = load_queue(QUEUE_PATH)
    summary = get_summary_report(queue)
    write_notification_file(run, summary)

    subject_parts = [f"{run.candidates_generated} candidates"]
    if run.contradictions_found:
        subject_parts.append(f"⚠ {run.contradictions_found} contradictions")
    if run.strong_candidates:
        subject_parts.append(f"{run.strong_candidates} strong")

    send_notification(
        subject=", ".join(subject_parts),
        body=Path("out/surveillance_notification.txt").read_text()
        if Path("out/surveillance_notification.txt").exists()
        else "Surveillance run complete.",
    )

    logger.info("Scheduled surveillance run complete. Run ID: %s", run.run_id)

    # Exit code signals urgency
    if run.contradictions_found > 0:
        sys.exit(2)   # 2 = needs urgent attention
    elif run.strong_candidates > 0:
        sys.exit(1)   # 1 = needs review
    else:
        sys.exit(0)   # 0 = all good


if __name__ == "__main__":
    main()
