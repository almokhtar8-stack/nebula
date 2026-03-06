"""
Nebula CLI entry point.

Commands:
  nebula run          — full analysis pipeline
  nebula validate-vcf — VCF QC check only
  nebula surveillance run    — run literature surveillance
  nebula surveillance review — show pending review queue
  nebula surveillance approve/reject — review a candidate
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from nebula.engine import compute_prs, evaluate_rules, load_ruleset
from nebula.ingestion import load_metadata, parse_vcf, run_qc
from nebula.report import build_report
from nebula.utils.io import write_json
from nebula.whitelist import extract_features, load_whitelist, whitelist_rsids

DEFAULT_WHITELIST = "data/whitelist/whitelist_v0_1.csv"
DEFAULT_RULESET = "rulesets/v0_1.yml"
DEFAULT_SURVEILLANCE_CONFIG = "rulesets/surveillance_config.yml"
DEFAULT_QUEUE_PATH = "out/surveillance_queue.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("nebula.cli")


@click.group()
@click.option("--debug", is_flag=True, default=False)
def cli(debug: bool) -> None:
    """Nebula — DNA-only precision wellness pipeline."""
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)


# ── PIPELINE ──────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--vcf", required=True, type=click.Path(exists=True))
@click.option("--meta", required=True, type=click.Path(exists=True))
@click.option("--whitelist", default=DEFAULT_WHITELIST, show_default=True, type=click.Path())
@click.option("--ruleset", default=DEFAULT_RULESET, show_default=True, type=click.Path())
@click.option("--out", default="out/", show_default=True, type=click.Path())
@click.option("--fail-on-qc", is_flag=True, default=False)
def run(vcf: str, meta: str, whitelist: str, ruleset: str, out: str, fail_on_qc: bool) -> None:
    """Run the full Nebula analysis pipeline → report.json"""
    click.echo("── Nebula Pipeline ─────────────────────────────────────")

    click.echo(f"[1/6] Loading whitelist: {whitelist}")
    wl_entries = load_whitelist(Path(whitelist))
    wl_rsids = whitelist_rsids(wl_entries)

    click.echo(f"[2/6] Parsing VCF: {vcf}")
    sample_id, genome_build, variants = parse_vcf(Path(vcf))

    click.echo(f"[3/6] Running QC for sample: {sample_id}")
    qc_result = run_qc(sample_id, genome_build, variants, wl_rsids)

    for w in qc_result.warnings:
        click.secho(f"  ⚠  QC Warning: {w}", fg="yellow")
    for e in qc_result.errors:
        click.secho(f"  ✗  QC Error: {e}", fg="red")
    if qc_result.errors and fail_on_qc:
        click.secho("QC failed — aborting (--fail-on-qc set).", fg="red")
        sys.exit(1)

    click.echo(f"[4/6] Loading metadata: {meta}")
    metadata = load_metadata(Path(meta))

    if metadata.sample_id != sample_id:
        click.secho(
            f"  ⚠  Sample ID mismatch: VCF='{sample_id}', metadata='{metadata.sample_id}'.",
            fg="yellow",
        )

    features = extract_features(wl_entries, variants)

    click.echo("[5/6] Computing PRS and evaluating rules...")
    ruleset_data = load_ruleset(Path(ruleset))
    prs_scores = compute_prs(features, metadata.sex_biological.value)
    rule_results = evaluate_rules(ruleset_data, features, prs_scores, metadata)

    click.echo(f"       {len(rule_results)} rules triggered: {[r.rule_id for r in rule_results]}")

    tier3 = [r for r in rule_results if r.output_tier.value == "tier_3"]
    if tier3:
        click.secho(
            f"  ⚠  TIER 3 FINDINGS: {[r.rule_id for r in tier3]} — human review required.",
            fg="red", bold=True,
        )

    click.echo("[6/6] Building report...")
    report = build_report(
        metadata=metadata,
        qc_result=qc_result,
        features=features,
        prs_scores=prs_scores,
        rule_results=rule_results,
        ruleset_version=str(ruleset_data["version"]),
    )

    out_path = Path(out) / "report.json"
    write_json(report.model_dump(), out_path)
    click.secho(f"\n✓ Report written to: {out_path}", fg="green", bold=True)
    click.echo(
        f"  Summary: {report.summary.total_insights} insights, "
        f"{report.summary.strong_evidence_count} strong, "
        f"{len(report.watchlist)} in watchlist."
    )


@cli.command("validate-vcf")
@click.option("--vcf", required=True, type=click.Path(exists=True))
def validate_vcf(vcf: str) -> None:
    """Validate a VCF and print QC summary. Exit 0 = pass, 1 = fail."""
    sample_id, genome_build, variants = parse_vcf(Path(vcf))
    qc = run_qc(sample_id, genome_build, variants, set())
    click.echo(json.dumps(qc.model_dump(), indent=2, default=str))
    sys.exit(0 if qc.overall_pass else 1)


# ── SURVEILLANCE ──────────────────────────────────────────────────────────────

@cli.group()
def surveillance() -> None:
    """Literature surveillance — monitor for new genomic evidence."""
    pass


@surveillance.command("run")
@click.option("--whitelist", default=DEFAULT_WHITELIST, show_default=True, type=click.Path())
@click.option("--config", default=DEFAULT_SURVEILLANCE_CONFIG, show_default=True, type=click.Path())
@click.option("--queue", default=DEFAULT_QUEUE_PATH, show_default=True, type=click.Path())
@click.option("--since", default=None, help="Only papers since YYYY/MM/DD")
@click.option("--ai-summaries", is_flag=True, default=False,
              help="Enable Claude API paper summaries (requires ANTHROPIC_API_KEY)")
@click.option("--dry-run", is_flag=True, default=False,
              help="Find and score but do not save to queue")
@click.option("--pubmed-key", default=None, envvar="NCBI_API_KEY",
              help="NCBI API key for higher rate limits")
def surveillance_run(
    whitelist: str,
    config: str,
    queue: str,
    since: str | None,
    ai_summaries: bool,
    dry_run: bool,
    pubmed_key: str | None,
) -> None:
    """
    Run a literature surveillance pass.

    Queries PubMed and GWAS Catalog for all rsIDs in the whitelist.
    New findings are scored and placed in the review queue.
    Nothing enters the product whitelist — a human must approve.
    """
    import yaml

    click.echo("── Nebula Surveillance ─────────────────────────────────")

    if dry_run:
        click.secho("DRY RUN — queue will NOT be modified", fg="yellow")

    # Load config
    config_path = Path(config)
    if config_path.exists():
        with config_path.open() as fh:
            cfg = yaml.safe_load(fh)
    else:
        click.secho(f"Config not found at {config} — using defaults", fg="yellow")
        cfg = {}

    from nebula.surveillance.runner import run_surveillance

    run = run_surveillance(
        whitelist_path=Path(whitelist),
        queue_path=Path(queue),
        config=cfg,
        use_ai_summaries=ai_summaries,
        since_date=since,
        pubmed_api_key=pubmed_key,
        dry_run=dry_run,
    )

    # Summary output
    click.echo("")
    click.secho("── Run Summary ─────────────────────────────────────────", bold=True)
    click.echo(f"  rsIDs checked:       {run.rsids_checked}")
    click.echo(f"  Papers found:        {run.papers_found}")
    click.echo(f"  GWAS hits found:     {run.gwas_hits_found}")
    click.echo(f"  Candidates queued:   {run.candidates_generated}")

    if run.strong_candidates > 0:
        click.secho(
            f"  Strong candidates:   {run.strong_candidates} ← review these first",
            fg="green", bold=True,
        )
    if run.contradictions_found > 0:
        click.secho(
            f"  Contradictions:      {run.contradictions_found} ← URGENT review",
            fg="red", bold=True,
        )
    if run.errors:
        click.secho(f"  Errors:              {len(run.errors)}", fg="yellow")
        for err in run.errors[:5]:
            click.secho(f"    - {err}", fg="yellow")

    if not dry_run:
        click.secho(
            f"\n✓ Queue saved to: {queue}",
            fg="green",
        )
        click.echo(
            f"  Run: nebula surveillance review --queue {queue}"
        )


@surveillance.command("review")
@click.option("--queue", default=DEFAULT_QUEUE_PATH, show_default=True, type=click.Path())
@click.option("--signal", default=None,
              help="Filter by signal: strong_candidate | contradicts | moderate_candidate")
@click.option("--pending-only", is_flag=True, default=True)
def surveillance_review(queue: str, signal: str | None, pending_only: bool) -> None:
    """Show the current surveillance review queue."""
    from nebula.surveillance.queue import load_queue, get_summary_report
    from nebula.surveillance.models import EvidenceSignal

    q = load_queue(Path(queue))
    summary = get_summary_report(q)

    click.secho("── Surveillance Queue ──────────────────────────────────", bold=True)
    click.echo(f"  Total candidates:    {summary['total_candidates']}")
    click.echo(f"  Pending review:      {summary['pending_review']}")
    click.echo(f"  Strong (pending):    {summary['strong_candidates_pending']}")
    click.echo(f"  Contradictions:      {summary['contradictions_pending']}")
    click.echo(f"  Approved:            {summary['approved']}")
    click.echo(f"  Rejected:            {summary['rejected']}")
    click.echo(f"  Last updated:        {summary['last_updated']}")
    click.echo("")

    candidates = q.pending() if pending_only else q.candidates

    if signal:
        try:
            sig_filter = EvidenceSignal(signal)
            candidates = [c for c in candidates if c.signal == sig_filter]
        except ValueError:
            click.secho(f"Unknown signal filter: {signal}", fg="red")
            sys.exit(1)

    if not candidates:
        click.secho("No candidates matching filter.", fg="green")
        return

    # Sort: contradictions first, then strong, then moderate
    def sort_key(c):
        order = {"contradicts": 0, "strong_candidate": 1, "moderate_candidate": 2}
        return order.get(c.signal.value, 3)

    candidates = sorted(candidates, key=sort_key)

    for c in candidates:
        signal_color = {
            "strong_candidate": "green",
            "contradicts": "red",
            "moderate_candidate": "yellow",
        }.get(c.signal.value, "white")

        click.echo("─" * 60)
        click.secho(
            f"  [{c.signal.value.upper()}]  {c.rsid}  —  {c.trait}",
            fg=signal_color, bold=True,
        )
        click.echo(f"  Gene: {c.gene or 'unknown'}")
        click.echo(f"  Auto score: {c.auto_score}/100")
        click.echo(f"  In whitelist: {c.already_in_whitelist}")
        if c.existing_evidence_grade:
            click.echo(f"  Current grade: {c.existing_evidence_grade}")
        if c.contradicts_existing:
            click.secho("  ⚠  CONTRADICTS EXISTING ENTRY", fg="red", bold=True)
        click.echo(f"  GWAS hits: {len(c.gwas_hits)}")
        click.echo(f"  Papers: {len(c.pubmed_papers)}")
        if c.score_reasons:
            click.echo("  Evidence signals:")
            for reason in c.score_reasons[:4]:
                click.echo(f"    • {reason}")
        if c.ai_summary:
            click.secho("  AI Summary:", bold=True)
            click.echo(f"    {c.ai_summary.three_sentence_summary}")
        click.echo(f"  Candidate ID: {c.candidate_id}")
        click.echo(f"  Found: {c.found_at[:10]}")

    click.echo("─" * 60)
    click.echo("")
    click.echo("To approve:  nebula surveillance approve --id <candidate_id>")
    click.echo("To reject:   nebula surveillance reject  --id <candidate_id>")


@surveillance.command("approve")
@click.option("--id", "candidate_id", required=True, help="Candidate ID to approve")
@click.option("--queue", default=DEFAULT_QUEUE_PATH, show_default=True, type=click.Path())
@click.option("--reviewer", default="unknown", help="Your name or identifier")
@click.option("--notes", default="", help="Review notes")
def surveillance_approve(
    candidate_id: str, queue: str, reviewer: str, notes: str
) -> None:
    """Approve a surveillance candidate for whitelist consideration."""
    from nebula.surveillance.queue import load_queue, approve_candidate, save_queue

    q = load_queue(Path(queue))
    if approve_candidate(q, candidate_id, reviewer, notes):
        save_queue(q, Path(queue))
        click.secho(f"✓ Approved: {candidate_id}", fg="green")
        click.echo("  Next step: manually add to whitelist CSV and increment version.")
    else:
        click.secho(f"Candidate not found: {candidate_id}", fg="red")
        sys.exit(1)


@surveillance.command("reject")
@click.option("--id", "candidate_id", required=True, help="Candidate ID to reject")
@click.option("--queue", default=DEFAULT_QUEUE_PATH, show_default=True, type=click.Path())
@click.option("--reviewer", default="unknown", help="Your name or identifier")
@click.option("--notes", default="", help="Reason for rejection")
def surveillance_reject(
    candidate_id: str, queue: str, reviewer: str, notes: str
) -> None:
    """Reject a surveillance candidate."""
    from nebula.surveillance.queue import load_queue, reject_candidate, save_queue

    q = load_queue(Path(queue))
    if reject_candidate(q, candidate_id, reviewer, notes):
        save_queue(q, Path(queue))
        click.secho(f"✓ Rejected: {candidate_id}", fg="yellow")
    else:
        click.secho(f"Candidate not found: {candidate_id}", fg="red")
        sys.exit(1)
