#!/usr/bin/env python3
"""
scripts/fetch_candidates.py
Automated surveillance feed — GWAS Catalog, ClinVar, PGS Catalog.

Usage:
    python scripts/fetch_candidates.py --dry-run
    python scripts/fetch_candidates.py --sources gwas clinvar pgs
    python scripts/fetch_candidates.py --queue-path data/surveillance_queue.json

Exit: 0=clean, 1=strong candidates found, 2=API error
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

# ── Load .env ─────────────────────────────────────────────────────────────────
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

from nebula.surveillance.models import (
    DataSource, EvidenceSignal, GWASHit, PubMedPaper, SurveillanceCandidate,
)
from nebula.surveillance.scorer import score_candidate
from nebula.surveillance.queue import load_queue, save_queue, merge_candidates
from nebula.whitelist.extractor import load_whitelist

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("nebula.fetch_candidates")

NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")
NCBI_BASE    = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
GWAS_BASE    = "https://www.ebi.ac.uk/gwas/rest/api"
PGS_BASE     = "https://www.pgscatalog.org/rest"

# Traits to watch — (efo_trait_string, short_label)
GWAS_TRAITS = [
    ("type 2 diabetes mellitus",  "T2D"),
    ("coronary artery disease",   "CAD"),
    ("breast carcinoma",          "BrCa"),
    ("celiac disease",            "Celiac"),
    ("chronotype",                "Sleep"),
    ("body mass index",           "BMI"),
    ("vitamin D measurement",     "VitD"),
    ("lactase persistence",       "LCT"),
    ("prostate carcinoma",        "PrCa"),
]

CLINVAR_TERMS = [
    ("hemochromatosis",       "Iron overload / HFE"),
    ("lactose intolerance",   "Lactose intolerance"),
    ("MTHFR",                 "Folate metabolism"),
    ("CYP1A2",                "Caffeine metabolism"),
    ("DPYD",                  "Fluoropyrimidine toxicity"),
    ("SLCO1B1",               "Statin myopathy"),
    ("vitamin D deficiency",  "Vitamin D"),
    ("celiac disease",        "Celiac / HLA"),
    ("COL5A1",                "Connective tissue"),
    ("FADS1",                 "Omega-3 metabolism"),
]

PGS_TRAITS = {
    "CAD":  ["EFO_0000270"],
    "T2D":  ["EFO_0001360"],
    "BrCa": ["EFO_0000305"],
    "PrCa": ["EFO_0001663"],
}

# ── HTTP ──────────────────────────────────────────────────────────────────────
def _get(url: str, params: dict | None = None, retries: int = 3) -> dict | None:
    if params:
        url = f"{url}?{urlencode(params)}"
    for attempt in range(retries):
        try:
            req = Request(url, headers={
                "Accept": "application/json",
                "User-Agent": "Nebula-Surveillance/0.1",
            })
            with urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except HTTPError as e:
            if e.code == 429:
                time.sleep(2 ** attempt)
            elif e.code in (400, 404):
                return None
            else:
                time.sleep(1)
        except Exception:
            time.sleep(1)
    return None

def _ncbi(endpoint: str, params: dict) -> dict | None:
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    params["retmode"] = "json"
    result = _get(f"{NCBI_BASE}/{endpoint}", params)
    time.sleep(0.12 if NCBI_API_KEY else 0.4)
    return result

# ── GWAS Catalog ──────────────────────────────────────────────────────────────
def fetch_gwas(whitelist: dict) -> list[SurveillanceCandidate]:
    logger.info("=== GWAS Catalog ===")
    candidates = []
    seen: set[str] = set()

    for trait_name, label in GWAS_TRAITS:
        logger.info("  %s", label)
        data = _get(
            f"{GWAS_BASE}/singleNucleotidePolymorphisms/search/findByEfoTrait",
            {"efoTrait": trait_name, "size": 50, "page": 0},
        )
        if not data:
            continue

        snps = data.get("_embedded", {}).get("singleNucleotidePolymorphisms", [])
        logger.info("    %d SNPs", len(snps))

        for snp in snps[:25]:
            rsid = snp.get("rsId", "")
            if not rsid or rsid in seen:
                continue
            seen.add(rsid)

            # Get associations for p-value
            assoc_data = _get(
                f"{GWAS_BASE}/singleNucleotidePolymorphisms/{rsid}/associations",
                {"size": 20},
            )
            time.sleep(0.3)
            if not assoc_data:
                continue

            assocs = assoc_data.get("_embedded", {}).get("associations", [])
            if not assocs:
                continue

            # Build GWASHit list — one per association
            hits: list[GWASHit] = []
            for a in assocs:
                try:
                    mantissa = float(a.get("pvalueMantissa") or 1)
                    exponent = int(a.get("pvalueExponent") or 0)
                    pval = mantissa * (10 ** exponent)
                    if pval > 5e-8:
                        continue

                    gene = ""
                    for gc in snp.get("genomicContexts", []):
                        g = gc.get("gene", {})
                        if g.get("geneName"):
                            gene = g["geneName"]
                            break

                    effect_allele = ""
                    for locus in a.get("loci", []):
                        for ra in locus.get("strongestRiskAlleles", []):
                            raw = ra.get("riskAlleleName", "")
                            if "-" in raw:
                                effect_allele = raw.split("-")[1]
                        break

                    or_val = a.get("orPerCopyNum")
                    beta = a.get("betaNum")

                    hits.append(GWASHit(
                        rsid=rsid,
                        trait=trait_name,
                        p_value=pval,
                        beta_or_or=float(or_val) if or_val else (float(beta) if beta else None),
                        effect_allele=effect_allele,
                        sample_size=0,
                        mapped_gene=gene,
                    ))
                except Exception:
                    continue

            if not hits:
                continue

            gene = hits[0].mapped_gene if hits else ""
            scored = score_candidate(
                rsid=rsid,
                trait=trait_name,
                gene=gene,
                gwas_hits=hits,
                papers=[],
                existing_whitelist=whitelist,
                candidate_id=f"gwas_{rsid}_{label}",
            )

            if scored.signal not in (EvidenceSignal.WEAK, EvidenceSignal.INSUFFICIENT_DATA):
                candidates.append(scored)
                tag = " [IN WHITELIST]" if scored.already_in_whitelist else ""
                logger.info("    + %s  %s  score=%d  %s%s",
                            rsid, trait_name[:35], scored.auto_score,
                            scored.signal.value, tag)

    logger.info("GWAS: %d candidates", len(candidates))
    return candidates


# ── ClinVar ───────────────────────────────────────────────────────────────────
def fetch_clinvar(whitelist: dict) -> list[SurveillanceCandidate]:
    logger.info("=== ClinVar ===")
    candidates = []
    seen: set[str] = set()

    for term, label in CLINVAR_TERMS:
        logger.info("  %s", label)

        search = _ncbi("esearch.fcgi", {
            "db": "clinvar",
            "term": (
                f'("{term}"[Gene/Protein name] OR "{term}"[Disease/Phenotype]) '
                f'AND ("pathogenic"[Clinical significance] OR '
                f'"likely pathogenic"[Clinical significance])'
            ),
            "retmax": 20,
        })
        if not search:
            continue

        ids = search.get("esearchresult", {}).get("idlist", [])
        if not ids:
            continue
        logger.info("    %d records", len(ids))

        summary = _ncbi("esummary.fcgi", {
            "db": "clinvar",
            "id": ",".join(ids[:15]),
        })
        if not summary:
            continue

        result = summary.get("result", {})
        uid_list = result.get("uids", [])

        for uid in uid_list:
            rec = result.get(str(uid))
            if not rec or not isinstance(rec, dict):
                continue

            # Check clinical significance — new API uses germline_classification
            sig_obj = rec.get("germline_classification") or rec.get("clinical_significance") or {}
            if not isinstance(sig_obj, dict):
                continue
            sig = sig_obj.get("description", "").lower()
            if "pathogenic" not in sig:
                continue

            # Gene
            gene = ""
            genes = rec.get("genes", [])
            if genes and isinstance(genes, list) and isinstance(genes[0], dict):
                gene = genes[0].get("symbol", "")

            # Trait from title
            title = rec.get("title", "")
            trait = label

            # Extract rsID from canonical_spdi via dbSNP lookup
            rsid = None
            for vs in rec.get("variation_set", []):
                if not isinstance(vs, dict):
                    continue

                # Try variation_xrefs first
                for xref in vs.get("variation_xrefs", []):
                    if not isinstance(xref, dict):
                        continue
                    if xref.get("db_source", "").lower() in ("dbsnp", "snp"):
                        db_id = xref.get("db_id", "")
                        if db_id:
                            rsid = f"rs{db_id}"
                            break

                # Fallback: dbSNP lookup via chromosomal position
                if not rsid:
                    spdi = vs.get("canonical_spdi", "")
                    if spdi and spdi.count(":") == 3:
                        accn, pos, ref, alt = spdi.split(":")
                        if ref and alt and len(ref) == 1 and len(alt) == 1:
                            snp_search = _ncbi("esearch.fcgi", {
                                "db": "snp",
                                "term": f"{accn}[ACCN] AND {pos}[CHRPOS38]",
                                "retmax": 1,
                            })
                            if snp_search:
                                snp_ids = snp_search.get("esearchresult", {}).get("idlist", [])
                                if snp_ids:
                                    rsid = f"rs{snp_ids[0]}"
                if rsid:
                    break

            if not rsid or rsid == "rs" or rsid in seen:
                continue
            seen.add(rsid)

            hit = GWASHit(
                rsid=rsid,
                trait=trait,
                p_value=1e-10,
                sample_size=10_000,
                mapped_gene=gene,
            )

            scored = score_candidate(
                rsid=rsid,
                trait=trait,
                gene=gene,
                gwas_hits=[hit],
                papers=[],
                existing_whitelist=whitelist,
                candidate_id=f"clinvar_{rsid}_{uid}",
            )

            if scored.signal != EvidenceSignal.WEAK:
                candidates.append(scored)
                tag = " [IN WHITELIST]" if scored.already_in_whitelist else ""
                logger.info("    + %s  %s  score=%d%s", rsid, trait[:30], scored.auto_score, tag)

    logger.info("ClinVar: %d candidates", len(candidates))
    return candidates


# ── PGS Catalog ───────────────────────────────────────────────────────────────
def fetch_pgs() -> dict[str, list[dict]]:
    logger.info("=== PGS Catalog ===")
    results: dict[str, list[dict]] = {}
    for condition, efo_ids in PGS_TRAITS.items():
        models: list[dict] = []
        for efo_id in efo_ids:
            data = _get(f"{PGS_BASE}/score/search", {"trait_id": efo_id, "limit": 10})
            if not data:
                continue
            for s in data.get("results", []):
                pgs_id = s.get("id", "")
                models.append({
                    "pgs_id":       pgs_id,
                    "num_variants": s.get("variants_number", 0),
                    "trait":        s.get("trait_reported", ""),
                    "ftp_url":      f"https://ftp.ebi.ac.uk/pub/databases/spot/pgs/scores/{pgs_id}/ScoringFiles/{pgs_id}.txt.gz",
                    "info_url":     f"https://www.pgscatalog.org/score/{pgs_id}/",
                })
        models.sort(key=lambda x: x["num_variants"], reverse=True)
        if models:
            results[condition] = models[:5]
            logger.info("  %s: top=%s (%d variants)",
                        condition, models[0]["pgs_id"], models[0]["num_variants"])
    return results


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-path",     default="data/surveillance_queue.json")
    parser.add_argument("--whitelist-path", default="data/whitelist/whitelist_v0_1.csv")
    parser.add_argument("--dry-run",        action="store_true")
    parser.add_argument("--sources", nargs="+",
                        choices=["gwas", "clinvar", "pgs"],
                        default=["gwas", "clinvar", "pgs"])
    args = parser.parse_args()

    if not NCBI_API_KEY:
        logger.warning("NCBI_API_KEY not set — rate limited to 3 req/s")

    # Load whitelist as dict[rsid -> WhitelistEntry] — what scorer expects
    whitelist: dict = {}
    wl_path = Path(args.whitelist_path)
    if wl_path.exists():
        try:
            entries = load_whitelist(wl_path)
            whitelist = {e.rsid: e for e in entries}
            logger.info("Whitelist: %d entries loaded", len(whitelist))
        except Exception as e:
            logger.warning("Could not load whitelist via load_whitelist: %s — using CSV fallback", e)
            with wl_path.open() as f:
                for row in csv.DictReader(f):
                    r = row.get("rsid", "").strip()
                    if r:
                        whitelist[r] = None  # type: ignore
            logger.info("Whitelist: %d rsIDs loaded (fallback)", len(whitelist))

    all_candidates: list[SurveillanceCandidate] = []
    pgs_models: dict = {}
    exit_code = 0

    if "gwas" in args.sources:
        try:
            all_candidates.extend(fetch_gwas(whitelist))
        except Exception as e:
            logger.error("GWAS failed: %s", e, exc_info=True)
            exit_code = 2

    if "clinvar" in args.sources:
        try:
            all_candidates.extend(fetch_clinvar(whitelist))
        except Exception as e:
            logger.error("ClinVar failed: %s", e, exc_info=True)
            exit_code = 2

    if "pgs" in args.sources:
        try:
            pgs_models = fetch_pgs()
        except Exception as e:
            logger.error("PGS failed: %s", e, exc_info=True)

    # ── Summary ───────────────────────────────────────────────────────────────
    strong   = [c for c in all_candidates if c.signal == EvidenceSignal.STRONG_CANDIDATE]
    moderate = [c for c in all_candidates if c.signal == EvidenceSignal.MODERATE_CANDIDATE]
    contras  = [c for c in all_candidates if c.signal == EvidenceSignal.CONTRADICTS_EXISTING]

    print("\n" + "═" * 62)
    print("NEBULA SURVEILLANCE RUN")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
          f"  |  sources: {', '.join(args.sources)}"
          f"  |  dry-run: {args.dry_run}")
    print("─" * 62)
    print(f"  Total candidates:       {len(all_candidates)}")
    print(f"  Strong (needs review):  {len(strong)}")
    print(f"  Moderate (watching):    {len(moderate)}")
    print(f"  Contradictions:         {len(contras)}")

    if strong:
        print("\n  STRONG CANDIDATES — counselor review required:")
        for c in strong:
            tag = " [ALREADY IN WHITELIST]" if c.already_in_whitelist else " [NEW]"
            print(f"    {c.rsid:15}  {c.trait[:38]:38}  score={c.auto_score}{tag}")

    if contras:
        print("\n  CONTRADICTIONS — existing entries may need re-review:")
        for c in contras:
            print(f"    {c.rsid:15}  {c.trait[:38]}")

    if moderate:
        print("\n  MODERATE — watching:")
        for c in moderate:
            tag = " [IN WHITELIST]" if c.already_in_whitelist else ""
            print(f"    {c.rsid:15}  {c.trait[:38]:38}  score={c.auto_score}{tag}")

    if pgs_models:
        print("\n  PGS CATALOG — replace synthetic weights in nebula/engine/prs.py:")
        for condition, models in pgs_models.items():
            top = models[0]
            print(f"    {condition}: {top['pgs_id']} ({top['num_variants']:,} variants)")
            print(f"      {top['ftp_url']}")

    # ── Write queue ───────────────────────────────────────────────────────────
    if not args.dry_run and all_candidates:
        q_path = Path(args.queue_path)
        queue = load_queue(q_path)
        before = len(queue.candidates)
        merge_candidates(queue, all_candidates)
        save_queue(queue, q_path)
        print(f"\n  Queue: {before} → {len(queue.candidates)} candidates")

    if not args.dry_run and pgs_models:
        out = Path("data/pgs_recommendations.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "models": pgs_models,
        }, indent=2))
        print(f"  PGS saved: {out}")

    if args.dry_run:
        print("\n  DRY RUN — queue not modified")

    print("═" * 62)

    if exit_code == 0 and (strong or contras):
        exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
