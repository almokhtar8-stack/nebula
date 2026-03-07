#!/usr/bin/env python3
"""
scripts/fetch_candidates.py
───────────────────────────
Automated weekly surveillance — finds new variant candidates from:
  1. GWAS Catalog  — genome-wide significant associations
  2. ClinVar       — pathogenic / likely-pathogenic variants
  3. PGS Catalog   — validated polygenic score models

Covers all Nebula wellness domains:
  Fitness · Nutrition · Sleep · Recovery · Pharmacogenomics · Health Risk

Usage:
    python scripts/fetch_candidates.py --dry-run
    python scripts/fetch_candidates.py --sources gwas clinvar pgs
    python scripts/fetch_candidates.py --sources gwas --category Fitness
    python scripts/fetch_candidates.py --queue-path data/surveillance_queue.json

Exit: 0 = clean,  1 = strong candidates found,  2 = API error
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
from urllib.error import HTTPError


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
    DataSource, EvidenceSignal, GWASHit, SurveillanceCandidate,
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


# ══════════════════════════════════════════════════════════════════════════════
# TRAIT CONFIGURATION — add traits here, no Python logic changes needed
# Format: (efo_trait_string, short_label, nebula_category)
# ══════════════════════════════════════════════════════════════════════════════

GWAS_TRAITS: list[tuple[str, str, str]] = [

    # ── FITNESS ───────────────────────────────────────────────────────────────
    ("physical activity measurement",       "PhysActivity",  "Fitness"),
    ("muscle strength",                     "MuscleStr",     "Fitness"),
    ("hand grip strength",                  "GripStrength",  "Fitness"),
    ("exercise tolerance",                  "ExTolerance",   "Fitness"),
    ("physical fitness",                    "PhysFitness",   "Fitness"),
    ("lean body mass",                      "LeanMass",      "Fitness"),
    ("tendon injury",                       "TendonInjury",  "Fitness"),
    ("anterior cruciate ligament injury",   "ACLInjury",     "Fitness"),

    # ── NUTRITION ─────────────────────────────────────────────────────────────
    ("caffeine consumption",                "Caffeine",      "Nutrition"),
    ("alcohol consumption",                 "Alcohol",       "Nutrition"),
    ("iron measurement",                    "Iron",          "Nutrition"),
    ("folate measurement",                  "Folate",        "Nutrition"),
    ("omega-3 fatty acid measurement",      "Omega3",        "Nutrition"),
    ("vitamin D measurement",               "VitD",          "Nutrition"),
    ("vitamin B12 measurement",             "VitB12",        "Nutrition"),
    ("lactase persistence",                 "LCT",           "Nutrition"),
    ("sugar intake",                        "Sugar",         "Nutrition"),
    ("dietary fibre intake",                "Fibre",         "Nutrition"),
    ("magnesium measurement",               "Magnesium",     "Nutrition"),
    ("choline measurement",                 "Choline",       "Nutrition"),
    ("body mass index",                     "BMI",           "Nutrition"),
    ("waist-hip ratio",                     "WHR",           "Nutrition"),

    # ── SLEEP & CIRCADIAN ─────────────────────────────────────────────────────
    ("chronotype",                          "Chronotype",    "Sleep"),
    ("sleep duration",                      "SleepDuration", "Sleep"),
    ("insomnia",                            "Insomnia",      "Sleep"),
    ("excessive daytime sleepiness",        "Sleepiness",    "Sleep"),
    ("restless legs syndrome",              "RLS",           "Sleep"),
    ("sleep apnea",                         "SleepApnea",    "Sleep"),

    # ── RECOVERY ─────────────────────────────────────────────────────────────
    ("inflammatory marker measurement",     "Inflammation",  "Recovery"),
    ("cortisol measurement",                "Cortisol",      "Recovery"),
    ("heart rate variability",              "HRV",           "Recovery"),

    # ── HEALTH RISK ───────────────────────────────────────────────────────────
    ("type 2 diabetes mellitus",            "T2D",           "Health Risk"),
    ("coronary artery disease",             "CAD",           "Health Risk"),
    ("hypertension",                        "HTN",           "Health Risk"),
    ("celiac disease",                      "Celiac",        "Health Risk"),
    ("obesity",                             "Obesity",       "Health Risk"),
    ("non-alcoholic fatty liver disease",   "NAFLD",         "Health Risk"),
    ("atrial fibrillation",                 "AFib",          "Health Risk"),
    ("gout",                                "Gout",          "Health Risk"),
    ("breast carcinoma",                    "BrCa",          "Health Risk"),
    ("prostate carcinoma",                  "PrCa",          "Health Risk"),
    ("colorectal cancer",                   "CRC",           "Health Risk"),

    # ── PHARMACOGENOMICS ─────────────────────────────────────────────────────
    ("drug response",                       "PGx",           "Pharmacogenomics"),
    ("statin response",                     "StatinRx",      "Pharmacogenomics"),
    ("warfarin response",                   "WarfarinRx",    "Pharmacogenomics"),
    ("clopidogrel response",                "CYP2C19rx",     "Pharmacogenomics"),
]

CLINVAR_TERMS: list[tuple[str, str, str]] = [
    # Pharmacogenomics — highest actionability
    ("DPYD",        "Fluoropyrimidine toxicity",  "Pharmacogenomics"),
    ("SLCO1B1",     "Statin myopathy",            "Pharmacogenomics"),
    ("CYP2C19",     "Clopidogrel / PPI response", "Pharmacogenomics"),
    ("CYP2D6",      "Opioid / antidepressant Rx", "Pharmacogenomics"),
    ("TPMT",        "Thiopurine toxicity",        "Pharmacogenomics"),
    ("NUDT15",      "Thiopurine toxicity",        "Pharmacogenomics"),
    ("G6PD",        "G6PD deficiency",            "Pharmacogenomics"),
    # Nutrition
    ("HFE",         "Hemochromatosis / iron",     "Nutrition"),
    ("MTHFR",       "Folate metabolism",          "Nutrition"),
    ("CYP1A2",      "Caffeine metabolism",        "Nutrition"),
    ("FADS1",       "Omega-3 metabolism",         "Nutrition"),
    ("VDR",         "Vitamin D receptor",         "Nutrition"),
    # Fitness
    ("COL5A1",      "Connective tissue / injury", "Fitness"),
    ("COL1A1",      "Collagen / bone",            "Fitness"),
    ("ACTN3",       "Muscle fiber type",          "Fitness"),
    # Health risk
    ("HLA-DQ",      "Celiac / HLA",               "Health Risk"),
    # Sleep
    ("CLOCK",       "Circadian rhythm",           "Sleep"),
    ("CRY1",        "Delayed sleep phase",        "Sleep"),
]

PGS_TRAITS: dict[str, list[str]] = {
    "CAD":    ["EFO_0000270", "EFO_0001645"],
    "T2D":    ["EFO_0001360", "MONDO_0005148"],
    "BrCa":   ["EFO_0000305"],
    "PrCa":   ["EFO_0001663"],
    "BMI":    ["EFO_0004340"],
    "Celiac": ["EFO_0001060"],
    "AFib":   ["EFO_0000275"],
    "CRC":    ["EFO_0005842"],
}


# ══════════════════════════════════════════════════════════════════════════════
# HTTP
# ══════════════════════════════════════════════════════════════════════════════

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


def _ncbi(ep: str, p: dict) -> dict | None:
    if NCBI_API_KEY:
        p["api_key"] = NCBI_API_KEY
    p["retmode"] = "json"
    r = _get(f"{NCBI_BASE}/{ep}", p)
    time.sleep(0.12 if NCBI_API_KEY else 0.4)
    return r


# ══════════════════════════════════════════════════════════════════════════════
# SOURCE 1 — GWAS CATALOG
# ══════════════════════════════════════════════════════════════════════════════

def fetch_gwas(whitelist: dict) -> list[SurveillanceCandidate]:
    logger.info("=== GWAS Catalog (%d traits) ===", len(GWAS_TRAITS))
    candidates: list[SurveillanceCandidate] = []
    seen: set[str] = set()

    for trait_name, label, category in GWAS_TRAITS:
        logger.info("  [%s] %s", category, label)

        data = _get(
            f"{GWAS_BASE}/singleNucleotidePolymorphisms/search/findByEfoTrait",
            {"efoTrait": trait_name, "size": 50, "page": 0},
        )
        if not data:
            continue

        snps = data.get("_embedded", {}).get("singleNucleotidePolymorphisms", [])
        if not snps:
            logger.info("    0 SNPs")
            continue
        logger.info("    %d SNPs", len(snps))

        for snp in snps[:25]:
            rsid = snp.get("rsId", "")
            if not rsid or rsid in seen:
                continue
            seen.add(rsid)

            assoc_data = _get(
                f"{GWAS_BASE}/singleNucleotidePolymorphisms/{rsid}/associations",
                {"size": 20},
            )
            time.sleep(0.3)
            if not assoc_data:
                continue

            assocs = assoc_data.get("_embedded", {}).get("associations", [])
            hits: list[GWASHit] = []

            for a in assocs:
                try:
                    pval = float(a.get("pvalueMantissa") or 1) * (
                        10 ** int(a.get("pvalueExponent") or 0)
                    )
                    if pval > 5e-8:
                        continue
                    gene = next(
                        (gc.get("gene", {}).get("geneName", "")
                         for gc in snp.get("genomicContexts", [])
                         if gc.get("gene", {}).get("geneName")),
                        "",
                    )
                    or_val = a.get("orPerCopyNum")
                    beta   = a.get("betaNum")
                    hits.append(GWASHit(
                        rsid=rsid,
                        trait=trait_name,
                        p_value=pval,
                        beta_or_or=(
                            float(or_val) if or_val else (float(beta) if beta else None)
                        ),
                        sample_size=0,
                        mapped_gene=gene,
                    ))
                except Exception:
                    continue

            if not hits:
                continue

            scored = score_candidate(
                rsid=rsid,
                trait=f"[{category}] {trait_name}",
                gene=hits[0].mapped_gene,
                gwas_hits=hits,
                papers=[],
                existing_whitelist=whitelist,
                candidate_id=f"gwas_{rsid}_{label}",
            )

            if scored.signal not in (EvidenceSignal.WEAK, EvidenceSignal.INSUFFICIENT_DATA):
                candidates.append(scored)
                logger.info("    + %s  score=%d  %s%s",
                            rsid, scored.auto_score, scored.signal.value,
                            "  [IN WHITELIST]" if scored.already_in_whitelist else "")

    logger.info("GWAS: %d candidates", len(candidates))
    return candidates


# ══════════════════════════════════════════════════════════════════════════════
# SOURCE 2 — CLINVAR
# ══════════════════════════════════════════════════════════════════════════════

def fetch_clinvar(whitelist: dict) -> list[SurveillanceCandidate]:
    logger.info("=== ClinVar (%d terms) ===", len(CLINVAR_TERMS))
    candidates: list[SurveillanceCandidate] = []
    seen: set[str] = set()

    for term, label, category in CLINVAR_TERMS:
        logger.info("  [%s] %s", category, label)

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

        summary = _ncbi("esummary.fcgi", {"db": "clinvar", "id": ",".join(ids[:15])})
        if not summary:
            continue

        result = summary.get("result", {})
        for uid in result.get("uids", []):
            rec = result.get(str(uid))
            if not rec or not isinstance(rec, dict):
                continue

            sig_obj = (
                rec.get("germline_classification")
                or rec.get("clinical_significance")
                or {}
            )
            if not isinstance(sig_obj, dict):
                continue
            if "pathogenic" not in sig_obj.get("description", "").lower():
                continue

            genes = rec.get("genes", [])
            gene  = genes[0].get("symbol", "") if genes and isinstance(genes[0], dict) else ""

            rsid = None
            for vs in rec.get("variation_set", []):
                if not isinstance(vs, dict):
                    continue
                for xref in vs.get("variation_xrefs", []):
                    if not isinstance(xref, dict):
                        continue
                    if xref.get("db_source", "").lower() in ("dbsnp", "snp"):
                        db_id = xref.get("db_id", "")
                        if db_id:
                            rsid = f"rs{db_id}"
                            break
                if not rsid:
                    spdi = vs.get("canonical_spdi", "")
                    if spdi and spdi.count(":") == 3:
                        accn, pos, ref, alt = spdi.split(":")
                        if ref and alt and len(ref) == 1 and len(alt) == 1:
                            sr = _ncbi("esearch.fcgi", {
                                "db": "snp",
                                "term": f"{accn}[ACCN] AND {pos}[CHRPOS38]",
                                "retmax": 1,
                            })
                            if sr:
                                snp_ids = sr.get("esearchresult", {}).get("idlist", [])
                                if snp_ids:
                                    rsid = f"rs{snp_ids[0]}"
                if rsid:
                    break

            if not rsid or rsid == "rs" or rsid in seen:
                continue
            seen.add(rsid)

            hit = GWASHit(
                rsid=rsid, trait=label,
                p_value=1e-10, sample_size=10_000, mapped_gene=gene,
            )
            scored = score_candidate(
                rsid=rsid,
                trait=f"[{category}] {label}",
                gene=gene,
                gwas_hits=[hit],
                papers=[],
                existing_whitelist=whitelist,
                candidate_id=f"clinvar_{rsid}_{uid}",
            )

            if scored.signal != EvidenceSignal.WEAK:
                candidates.append(scored)
                logger.info("    + %s  score=%d%s",
                            rsid, scored.auto_score,
                            "  [IN WHITELIST]" if scored.already_in_whitelist else "")

    logger.info("ClinVar: %d candidates", len(candidates))
    return candidates


# ══════════════════════════════════════════════════════════════════════════════
# SOURCE 3 — PGS CATALOG
# ══════════════════════════════════════════════════════════════════════════════

def fetch_pgs() -> dict[str, list[dict]]:
    logger.info("=== PGS Catalog (%d conditions) ===", len(PGS_TRAITS))
    results: dict[str, list[dict]] = {}

    for condition, efo_ids in PGS_TRAITS.items():
        models: list[dict] = []
        for efo_id in efo_ids:
            data = _get(f"{PGS_BASE}/score/search", {"trait_id": efo_id, "limit": 10})
            if not data:
                continue
            for s in data.get("results", []):
                pid = s.get("id", "")
                models.append({
                    "pgs_id":       pid,
                    "num_variants": s.get("variants_number", 0),
                    "trait":        s.get("trait_reported", ""),
                    "ftp_url": (
                        f"https://ftp.ebi.ac.uk/pub/databases/spot/pgs/scores/"
                        f"{pid}/ScoringFiles/{pid}.txt.gz"
                    ),
                    "info_url": f"https://www.pgscatalog.org/score/{pid}/",
                })
        models.sort(key=lambda x: x["num_variants"], reverse=True)
        if models:
            results[condition] = models[:5]
            logger.info("  %s: %s (%d variants)",
                        condition, models[0]["pgs_id"], models[0]["num_variants"])

    return results


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Nebula surveillance — finds new variant candidates weekly"
    )
    parser.add_argument("--queue-path",     default="data/surveillance_queue.json")
    parser.add_argument("--whitelist-path", default="data/whitelist/whitelist_v0_1.csv")
    parser.add_argument("--dry-run",        action="store_true")
    parser.add_argument("--sources", nargs="+",
                        choices=["gwas", "clinvar", "pgs"],
                        default=["gwas", "clinvar", "pgs"])
    parser.add_argument("--category", default=None,
                        help="Filter: Fitness | Nutrition | Sleep | Recovery | "
                             "Health Risk | Pharmacogenomics")
    args = parser.parse_args()

    if not NCBI_API_KEY:
        logger.warning("NCBI_API_KEY not set — ClinVar will be rate-limited")

    # Load whitelist
    whitelist: dict = {}
    wl_path = Path(args.whitelist_path)
    if wl_path.exists():
        try:
            entries = load_whitelist(wl_path)
            whitelist = {e.rsid: e for e in entries}
            logger.info("Whitelist: %d entries", len(whitelist))
        except Exception as e:
            logger.warning("load_whitelist failed (%s) — CSV fallback", e)
            with wl_path.open() as f:
                for row in csv.DictReader(f):
                    r = row.get("rsid", "").strip()
                    if r:
                        whitelist[r] = None  # type: ignore
            logger.info("Whitelist: %d rsIDs (fallback)", len(whitelist))

    # Category filter
    global GWAS_TRAITS, CLINVAR_TERMS
    if args.category:
        cat = args.category.strip()
        GWAS_TRAITS   = [(t, l, c) for t, l, c in GWAS_TRAITS   if c == cat]
        CLINVAR_TERMS = [(t, l, c) for t, l, c in CLINVAR_TERMS if c == cat]
        logger.info("Category filter '%s': %d GWAS, %d ClinVar",
                    cat, len(GWAS_TRAITS), len(CLINVAR_TERMS))

    all_candidates: list[SurveillanceCandidate] = []
    pgs_models: dict = {}
    exit_code = 0

    if "gwas"    in args.sources:
        try:    all_candidates.extend(fetch_gwas(whitelist))
        except Exception as e:
            logger.error("GWAS failed: %s", e, exc_info=True); exit_code = 2

    if "clinvar" in args.sources:
        try:    all_candidates.extend(fetch_clinvar(whitelist))
        except Exception as e:
            logger.error("ClinVar failed: %s", e, exc_info=True); exit_code = 2

    if "pgs"     in args.sources:
        try:    pgs_models = fetch_pgs()
        except Exception as e:
            logger.error("PGS failed: %s", e, exc_info=True)

    strong   = [c for c in all_candidates if c.signal == EvidenceSignal.STRONG_CANDIDATE]
    moderate = [c for c in all_candidates if c.signal == EvidenceSignal.MODERATE_CANDIDATE]
    contras  = [c for c in all_candidates if c.signal == EvidenceSignal.CONTRADICTS_EXISTING]

    # Group by category
    by_cat: dict[str, int] = {}
    for c in all_candidates:
        cat = c.trait.split("]")[0].lstrip("[") if c.trait.startswith("[") else "Other"
        by_cat[cat] = by_cat.get(cat, 0) + 1

    print("\n" + "═" * 64)
    print("NEBULA SURVEILLANCE RUN")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
          f"  |  sources: {', '.join(args.sources)}"
          f"  |  dry-run: {args.dry_run}")
    print("─" * 64)
    print(f"  Total:         {len(all_candidates)}")
    print(f"  Strong:        {len(strong)}   ← counselor review needed")
    print(f"  Moderate:      {len(moderate)}  ← watching")
    print(f"  Contradicts:   {len(contras)}   ← urgent if >0")

    if by_cat:
        print("\n  BY CATEGORY:")
        for cat, n in sorted(by_cat.items()):
            print(f"    {cat:<20} {n}")

    if strong:
        print("\n  ⚠  STRONG — needs counselor review before accepting:")
        for c in strong:
            print(f"    {c.rsid:15} {c.trait[:42]:42} score={c.auto_score}"
                  f"{'  [IN WHITELIST]' if c.already_in_whitelist else '  [NEW]'}")

    if contras:
        print("\n  ⚠  CONTRADICTIONS — re-review existing whitelist entries:")
        for c in contras:
            print(f"    {c.rsid:15} {c.trait[:42]}")

    if moderate:
        print("\n  MODERATE — review via: python scripts/review_queue.py --list")
        for c in moderate:
            print(f"    {c.rsid:15} {c.trait[:42]:42} score={c.auto_score}"
                  f"{'  [WL]' if c.already_in_whitelist else ''}")

    if pgs_models:
        print("\n  PGS CATALOG — updated weights available:")
        for cond, models in pgs_models.items():
            t = models[0]
            print(f"    {cond:<8} {t['pgs_id']}  ({t['num_variants']:,} variants)")
            print(f"             {t['ftp_url']}")

    # Write queue
    if not args.dry_run and all_candidates:
        q_path = Path(args.queue_path)
        q = load_queue(q_path)
        before = len(q.candidates)
        merge_candidates(q, all_candidates)
        save_queue(q, q_path)
        added = len(q.candidates) - before
        print(f"\n  Queue: {before} → {len(q.candidates)} (+{added} new)")
        print(f"  Review with: python scripts/review_queue.py --list")

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

    print("═" * 64)
    return 1 if (strong or contras) else exit_code


if __name__ == "__main__":
    sys.exit(main())
