#!/usr/bin/env python3
"""
scripts/review_queue.py
───────────────────────
Human review tool for surveillance candidates.

When you ACCEPT a candidate it automatically:
  1. Adds the rsID to data/whitelist/whitelist_v0_1.csv
  2. Writes a rule stub to rulesets/pending_rules.yml (counselor fills details)
  3. Marks candidate as APPROVED in surveillance_queue.json
  4. Logs decision with timestamp

When you REJECT a candidate it:
  1. Marks as REJECTED with your reason
  2. Never resurfaces in future surveillance runs

Usage:
    python scripts/review_queue.py --list
    python scripts/review_queue.py --list --category Fitness
    python scripts/review_queue.py --accept gwas_rs17883331_T2D
    python scripts/review_queue.py --reject gwas_rs562138031_BMI --reason "low MAF, not actionable"
    python scripts/review_queue.py --interactive
    python scripts/review_queue.py --stats
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml  # pip install pyyaml

def _load_env(root: Path) -> None:
    env = root / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

_load_env(Path(__file__).parent.parent)
sys.path.insert(0, str(Path(__file__).parent.parent))

from nebula.surveillance.models import EvidenceSignal, ReviewStatus
from nebula.surveillance.queue import (
    load_queue, save_queue, approve_candidate, reject_candidate, get_summary_report,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("nebula.review_queue")

PROJECT_ROOT   = Path(__file__).parent.parent
QUEUE_PATH     = PROJECT_ROOT / "data" / "surveillance_queue.json"
WHITELIST_PATH = PROJECT_ROOT / "data" / "whitelist" / "whitelist_v0_1.csv"
PENDING_RULES  = PROJECT_ROOT / "rulesets" / "pending_rules.yml"
REVIEW_LOG     = PROJECT_ROOT / "data" / "review_log.jsonl"

SIGNAL_EMOJI = {
    EvidenceSignal.STRONG_CANDIDATE:    "🔴",
    EvidenceSignal.MODERATE_CANDIDATE:  "🟡",
    EvidenceSignal.CONTRADICTS_EXISTING:"⚠️ ",
    EvidenceSignal.WEAK:                "⚪",
    EvidenceSignal.INSUFFICIENT_DATA:   "⚪",
}


# ── Whitelist writer ──────────────────────────────────────────────────────────

def _append_to_whitelist(
    rsid: str,
    gene: str,
    category: str,
    trait: str,
    notes: str = "",
) -> None:
    """Append a new accepted variant to the whitelist CSV."""
    WHITELIST_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Read existing to check for duplicates
    existing_rsids: set[str] = set()
    if WHITELIST_PATH.exists():
        with WHITELIST_PATH.open() as f:
            for row in csv.DictReader(f):
                existing_rsids.add(row.get("rsid", "").strip())

    if rsid in existing_rsids:
        logger.warning("%s already in whitelist — skipping CSV append", rsid)
        return

    # Normalise category to whitelist convention
    category = category.lstrip("[").rstrip("]").strip()

    with WHITELIST_PATH.open("a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            rsid,
            gene or "Unknown",
            category,
            trait,
            "",           # risk_allele — counselor fills
            "",           # ref_allele  — counselor fills
            "Exploratory",# evidence_grade — conservative default
            notes or f"Added by surveillance {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        ])

    logger.info("Appended %s to whitelist", rsid)


# ── Rule stub writer ──────────────────────────────────────────────────────────

def _write_rule_stub(
    rsid: str,
    gene: str,
    trait: str,
    category: str,
    candidate_id: str,
    score: int,
) -> None:
    """Append a commented rule stub to pending_rules.yml for counselor completion."""
    PENDING_RULES.parent.mkdir(parents=True, exist_ok=True)

    # Determine next rule ID
    prefix_map = {
        "Fitness":         "FIT",
        "Nutrition":       "NUT",
        "Sleep":           "REC",
        "Recovery":        "REC",
        "Health Risk":     "RISK",
        "Pharmacogenomics":"RISK",
    }
    prefix = prefix_map.get(category, "RISK")

    # Count existing stubs to increment ID
    existing_count = 0
    if PENDING_RULES.exists():
        content = PENDING_RULES.read_text()
        existing_count = content.count(f"  - id: {prefix}-")

    rule_num = 100 + existing_count  # pending rules start at 100 to avoid clash
    rule_id  = f"{prefix}-{rule_num:03d}-PENDING"
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    stub = f"""
  # ── AUTO-GENERATED STUB — counselor review required ──────────────────────
  # Source:      surveillance candidate {candidate_id}
  # rsID:        {rsid}
  # Gene:        {gene or 'Unknown'}
  # Trait:       {trait}
  # Auto score:  {score}
  # Added:       {date_str}
  # TODO: Fill in recommendation_text, practical_action, confidence,
  #       required_data, and set evidence_grade before moving to v0_1.yml

  - id: {rule_id}
    category: {category}
    description: >
      [FILL IN] {gene or rsid} variant — {trait}
    trigger: {rule_id}     # TODO: implement trigger in nebula/engine/evaluator.py
    required_data:
      - "DNA: {rsid}"
    data_sources:
      - "DNA: {gene or rsid} {rsid}"
    recommendation_text: >
      [FILL IN] Description of what this genetic variant means for the user.
    reason: >
      [FILL IN] Scientific rationale citing key studies.
    evidence_grade: Exploratory
    base_confidence: 60
    practical_action: >
      [FILL IN] What should the user actually do?
    review_interval: "Annual — re-evaluate as evidence develops."
    disclaimer: >
      This finding is based on emerging evidence and should be interpreted
      with caution. Consult a healthcare provider before making changes.
    referral_trigger: false
    output_tier: tier_1
    # Surveillance metadata
    surveillance_candidate_id: {candidate_id}
    surveillance_auto_score: {score}
    surveillance_added: "{date_str}"
"""

    with PENDING_RULES.open("a") as f:
        if not PENDING_RULES.exists() or PENDING_RULES.stat().st_size == 0:
            f.write("# Pending rule stubs — generated by review_queue.py\n")
            f.write("# Counselor: fill in each stub then move to rulesets/v0_1.yml\n")
            f.write("pending_rules:\n")
        f.write(stub)

    logger.info("Rule stub written to %s", PENDING_RULES)


# ── Audit log ─────────────────────────────────────────────────────────────────

def _log_decision(
    action: str,
    rsid: str,
    candidate_id: str,
    reviewer: str,
    reason: str = "",
) -> None:
    REVIEW_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "action":       action,
        "rsid":         rsid,
        "candidate_id": candidate_id,
        "reviewer":     reviewer,
        "reason":       reason,
    }
    with REVIEW_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")


# ── Display helpers ───────────────────────────────────────────────────────────

def _print_candidate(c, index: int | None = None) -> None:
    prefix = f"[{index}] " if index is not None else ""
    emoji  = SIGNAL_EMOJI.get(c.signal, "  ")
    wl_tag = "  [IN WHITELIST]" if c.already_in_whitelist else ""
    print(f"\n{prefix}{emoji} {c.rsid}  |  {c.trait}{wl_tag}")
    print(f"   ID:     {c.candidate_id}")
    print(f"   Gene:   {c.gene or 'Unknown'}")
    print(f"   Score:  {c.auto_score}/100")
    print(f"   Signal: {c.signal.value}")
    if c.gwas_hits:
        best = min(c.gwas_hits, key=lambda h: h.p_value)
        print(f"   Best p: {best.p_value:.2e}")
    if c.score_reasons:
        print("   Reasons:")
        for r in c.score_reasons[:4]:
            print(f"     • {r}")
    print(f"   Review: python scripts/review_queue.py --accept {c.candidate_id}")
    print(f"           python scripts/review_queue.py --reject {c.candidate_id} --reason '...'")


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_list(args) -> None:
    queue = load_queue(QUEUE_PATH)
    pending = queue.pending()

    if args.category:
        cat = args.category.lower()
        pending = [c for c in pending if cat in c.trait.lower()]

    strong   = [c for c in pending if c.signal == EvidenceSignal.STRONG_CANDIDATE]
    moderate = [c for c in pending if c.signal == EvidenceSignal.MODERATE_CANDIDATE]
    contras  = [c for c in pending if c.signal == EvidenceSignal.CONTRADICTS_EXISTING]

    print(f"\n{'═'*64}")
    print(f"NEBULA REVIEW QUEUE  —  {len(pending)} pending")
    if args.category:
        print(f"Filtered to: {args.category}")
    print(f"{'─'*64}")
    print(f"  Strong:       {len(strong)}   ← review these first")
    print(f"  Moderate:     {len(moderate)}")
    print(f"  Contradicts:  {len(contras)}  ← urgent")
    print(f"{'─'*64}")

    for group, label in [(strong, "STRONG"), (contras, "CONTRADICTIONS"), (moderate, "MODERATE")]:
        if not group:
            continue
        print(f"\n  {label}:")
        for c in group:
            emoji  = SIGNAL_EMOJI.get(c.signal, "  ")
            wl_tag = " [WL]" if c.already_in_whitelist else ""
            print(f"    {emoji} {c.rsid:15} {c.trait[:40]:40} score={c.auto_score}{wl_tag}")
            print(f"       id: {c.candidate_id}")

    print(f"\n  To review: python scripts/review_queue.py --interactive")
    print(f"{'═'*64}")


def cmd_accept(args) -> None:
    reviewer = args.reviewer or os.environ.get("USER", "unknown")
    queue = load_queue(QUEUE_PATH)

    # Find candidate
    cand = next((c for c in queue.candidates if c.candidate_id == args.accept), None)
    if not cand:
        print(f"ERROR: candidate '{args.accept}' not found in queue")
        print("Run --list to see candidate IDs")
        sys.exit(1)

    # Parse category from trait string
    category = cand.trait.split("]")[0].lstrip("[").strip() if cand.trait.startswith("[") else "Health Risk"
    trait_clean = cand.trait.split("] ")[-1] if "] " in cand.trait else cand.trait

    print(f"\nACCEPTING: {cand.rsid}")
    print(f"  Gene:     {cand.gene or 'Unknown'}")
    print(f"  Trait:    {cand.trait}")
    print(f"  Score:    {cand.auto_score}")
    print(f"  Category: {category}")
    print()

    # 1. Add to whitelist
    _append_to_whitelist(
        rsid=cand.rsid,
        gene=cand.gene or "",
        category=category,
        trait=trait_clean,
        notes=args.notes or "",
    )

    # 2. Write rule stub
    _write_rule_stub(
        rsid=cand.rsid,
        gene=cand.gene or "",
        trait=trait_clean,
        category=category,
        candidate_id=cand.candidate_id,
        score=cand.auto_score,
    )

    # 3. Mark approved in queue
    approve_candidate(queue, args.accept, reviewer=reviewer, notes=args.notes or "")
    save_queue(queue, QUEUE_PATH)

    # 4. Audit log
    _log_decision("ACCEPT", cand.rsid, args.accept, reviewer, args.notes or "")

    print(f"✓ {cand.rsid} accepted")
    print(f"  Added to:  {WHITELIST_PATH}")
    print(f"  Rule stub: {PENDING_RULES}")
    print(f"  Next step: open {PENDING_RULES} and fill in the rule stub,")
    print(f"             then move it to rulesets/v0_1.yml")


def cmd_reject(args) -> None:
    reviewer = args.reviewer or os.environ.get("USER", "unknown")
    reason   = args.reason or "No reason given"
    queue    = load_queue(QUEUE_PATH)

    cand = next((c for c in queue.candidates if c.candidate_id == args.reject), None)
    if not cand:
        print(f"ERROR: candidate '{args.reject}' not found")
        sys.exit(1)

    reject_candidate(queue, args.reject, reviewer=reviewer, notes=reason)
    save_queue(queue, QUEUE_PATH)
    _log_decision("REJECT", cand.rsid, args.reject, reviewer, reason)

    print(f"✗ {cand.rsid} rejected — will not reappear in future runs")
    print(f"  Reason: {reason}")


def cmd_interactive(args) -> None:
    reviewer = args.reviewer or os.environ.get("USER", "unknown")
    queue    = load_queue(QUEUE_PATH)
    pending  = queue.pending()

    if not pending:
        print("No pending candidates to review.")
        return

    # Sort: strong first, then by score desc
    pending.sort(key=lambda c: (
        0 if c.signal == EvidenceSignal.STRONG_CANDIDATE else
        1 if c.signal == EvidenceSignal.CONTRADICTS_EXISTING else 2,
        -c.auto_score,
    ))

    print(f"\n{'═'*64}")
    print(f"INTERACTIVE REVIEW — {len(pending)} pending candidates")
    print("Commands: a=accept  r=reject  s=skip  q=quit")
    print(f"{'═'*64}")

    accepted = rejected = skipped = 0

    for i, cand in enumerate(pending):
        _print_candidate(cand, index=i + 1)
        print(f"\n  ({i+1}/{len(pending)})  [a]ccept / [r]eject / [s]kip / [q]uit: ", end="", flush=True)

        try:
            choice = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            break

        if choice == "q":
            print("Quit.")
            break
        elif choice == "a":
            notes_prompt = "  Acceptance notes (Enter to skip): "
            print(notes_prompt, end="", flush=True)
            try:
                notes = input().strip()
            except (EOFError, KeyboardInterrupt):
                notes = ""

            category = (
                cand.trait.split("]")[0].lstrip("[").strip()
                if cand.trait.startswith("[") else "Health Risk"
            )
            trait_clean = cand.trait.split("] ")[-1] if "] " in cand.trait else cand.trait

            _append_to_whitelist(cand.rsid, cand.gene or "", category, trait_clean, notes)
            _write_rule_stub(cand.rsid, cand.gene or "", trait_clean, category, cand.candidate_id, cand.auto_score)
            approve_candidate(queue, cand.candidate_id, reviewer=reviewer, notes=notes)
            _log_decision("ACCEPT", cand.rsid, cand.candidate_id, reviewer, notes)
            print(f"  ✓ Accepted {cand.rsid}")
            accepted += 1

        elif choice == "r":
            reason_prompt = "  Rejection reason: "
            print(reason_prompt, end="", flush=True)
            try:
                reason = input().strip() or "No reason given"
            except (EOFError, KeyboardInterrupt):
                reason = "No reason given"

            reject_candidate(queue, cand.candidate_id, reviewer=reviewer, notes=reason)
            _log_decision("REJECT", cand.rsid, cand.candidate_id, reviewer, reason)
            print(f"  ✗ Rejected {cand.rsid}")
            rejected += 1

        else:  # skip
            print(f"  → Skipped {cand.rsid}")
            skipped += 1

    save_queue(queue, QUEUE_PATH)
    print(f"\n{'─'*64}")
    print(f"Session complete: {accepted} accepted, {rejected} rejected, {skipped} skipped")
    if accepted:
        print(f"\nNext step: fill in rule stubs in {PENDING_RULES}")
        print("           then move completed rules to rulesets/v0_1.yml")


def cmd_stats(args) -> None:
    queue = load_queue(QUEUE_PATH)
    report = get_summary_report(queue)

    print(f"\n{'═'*50}")
    print("NEBULA SURVEILLANCE STATS")
    print(f"{'─'*50}")
    for k, v in report.items():
        print(f"  {k:<30} {v}")

    # Show review log summary
    if REVIEW_LOG.exists():
        entries = [json.loads(l) for l in REVIEW_LOG.read_text().splitlines() if l.strip()]
        accepts = [e for e in entries if e["action"] == "ACCEPT"]
        rejects = [e for e in entries if e["action"] == "REJECT"]
        print(f"\n  REVIEW LOG:")
        print(f"  {'Total decisions:':<30} {len(entries)}")
        print(f"  {'Accepted:':<30} {len(accepts)}")
        print(f"  {'Rejected:':<30} {len(rejects)}")
        if entries:
            print(f"  {'Last decision:':<30} {entries[-1]['timestamp'][:10]}")
    print(f"{'═'*50}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Nebula review queue — accept or reject surveillance candidates"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list",        action="store_true",  help="List pending candidates")
    group.add_argument("--interactive", action="store_true",  help="Review one by one")
    group.add_argument("--accept",      metavar="CANDIDATE_ID", help="Accept a candidate")
    group.add_argument("--reject",      metavar="CANDIDATE_ID", help="Reject a candidate")
    group.add_argument("--stats",       action="store_true",  help="Show queue statistics")

    parser.add_argument("--reason",   default="",   help="Rejection reason")
    parser.add_argument("--notes",    default="",   help="Acceptance notes")
    parser.add_argument("--reviewer", default=None, help="Reviewer name (default: $USER)")
    parser.add_argument("--category", default=None,
                        help="Filter: Fitness | Nutrition | Sleep | Health Risk | Pharmacogenomics")

    args = parser.parse_args()

    if args.list:
        cmd_list(args)
    elif args.interactive:
        cmd_interactive(args)
    elif args.accept:
        cmd_accept(args)
    elif args.reject:
        cmd_reject(args)
    elif args.stats:
        cmd_stats(args)


if __name__ == "__main__":
    main()
