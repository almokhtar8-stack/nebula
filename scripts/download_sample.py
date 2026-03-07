#!/usr/bin/env python3
"""
scripts/download_sample.py
──────────────────────────
Downloads a filtered VCF for a 1000 Genomes sample covering only the
Nebula whitelist positions.  Uses bcftools HTTP streaming — downloads
~200KB instead of the full 50GB genome.

Requirements:
    conda install -c bioconda bcftools   # or: sudo apt install bcftools

Usage:
    python scripts/download_sample.py
    python scripts/download_sample.py --sample HG00096 --out data/vcf/HG00096.vcf
    python scripts/download_sample.py --list-samples
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

# ── 1000 Genomes high-coverage phased VCF URLs (GRCh38) ──────────────────────
BASE_URL = (
    "https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/"
    "1000G_2504_high_coverage/working/20201028_3202_phased/"
    "CCDG_14151_B01_GRM_WGS_2020-08-05_chr{chrom}"
    ".filtered.shapeit2-duohmm-phased.vcf.gz"
)

# ── GRCh38 positions for every whitelist rsID ─────────────────────────────────
# Format: rsid -> (chrom, pos)
RSID_POSITIONS: dict[str, tuple[str, int]] = {
    # Caffeine
    "rs762551":   ("15",  74748057),
    "rs4410790":  ("7",   17284295),
    "rs5751876":  ("22",  24787490),
    # Alcohol
    "rs671":      ("12", 111803962),
    "rs1229984":  ("4",  100178894),
    # Lactose
    "rs4988235":  ("2",  135851076),
    # B-Vitamins / Folate
    "rs1801133":  ("1",   11856378),   # MTHFR C677T
    "rs1801131":  ("1",   11854476),   # MTHFR A1298C
    "rs602662":   ("19",  49206417),   # FUT2 / B12
    # Vitamin D
    "rs1544410":  ("12",  47809446),   # VDR BsmI
    "rs10741657": ("11",  14911684),   # CYP2R1
    "rs2282679":  ("4",   72608784),   # GC / DBP
    "rs12785878": ("11",  71160352),   # DHCR7
    # Nutrition / Metabolism
    "rs9939609":  ("16",  53820527),   # FTO
    "rs174546":   ("11",  61804851),   # FADS1
    "rs1800562":  ("6",   26090951),   # HFE C282Y
    "rs1799945":  ("6",   26093141),   # HFE H63D
    "rs4988458":  ("3",   12393125),   # PPARG Pro12Ala
    # Breast cancer PRS
    "rs2981582":  ("10", 121577821),
    "rs3803662":  ("16",  52599188),
    "rs889312":   ("5",   56048031),
    # CAD PRS
    "rs1333049":  ("9",   22115503),
    "rs10757278": ("9",   22125855),
    "rs2943634":  ("9",  136141870),
    "rs9982601":  ("15",  67358170),
    # T2D PRS
    "rs7903146":  ("10", 112998590),   # TCF7L2
    "rs1111875":  ("10",  94462882),   # HHEX
    "rs5219":     ("11",  17409572),   # KCNJ11
    "rs13266634": ("8",  117172544),   # SLC30A8
    # Prostate cancer PRS
    "rs1447295":  ("8",  128543429),
    "rs16901979": ("8",  128614977),
    "rs6983267":  ("8",  128482487),
    # Fitness
    "rs1815739":  ("11",  66560624),   # ACTN3
    "rs12722":    ("9",  134646690),   # COL5A1
    "rs1800795":  ("7",   22766645),   # IL6
    # Sleep / Circadian
    "rs2304672":  ("2",  239173806),   # PER2
    "rs1801260":  ("4",   56027980),   # CLOCK
    "rs73598374": ("20",  44531735),   # ADA
    # Pharmacogenomics
    "rs4149056":  ("12",  21329064),   # SLCO1B1 (statin)
    "rs3918290":  ("1",   97915614),   # DPYD
    "rs1057910":  ("10",  94942290),   # CYP2C9 *3
    "rs1799853":  ("10",  94981296),   # CYP2C9 *2
    "rs4244285":  ("10",  94781859),   # CYP2C19 *2
    "rs12248560": ("10",  94762681),   # CYP2C19 *17
    "rs9923231":  ("16",  31096368),   # VKORC1
    # Celiac / HLA
    "rs2187668":  ("6",   32690633),   # HLA-DQ2
    "rs7454108":  ("6",   32713961),   # HLA-DQ8
    # APOE
    "rs7412":     ("19",  44908684),
    "rs429358":   ("19",  44908822),
    # Immune
    "rs1800871":  ("1",  206946762),   # IL10
    "rs2234767":  ("10",  90748105),   # CD95/FAS
}

# Well-characterised 1000 Genomes samples
KNOWN_SAMPLES = {
    "HG00096": "European (GBR) — male",
    "HG00097": "European (GBR) — female",
    "NA19240": "African (YRI) — female",
    "NA12878": "European (CEU) — female (reference sample)",
    "HG01565": "South Asian (PJL) — male",
    "HG00514": "East Asian (CHS) — male",
}


def check_bcftools() -> bool:
    return shutil.which("bcftools") is not None


def install_hint() -> None:
    print("\nBcftools is required. Install it with one of:")
    print("  conda install -c bioconda bcftools")
    print("  sudo apt install bcftools")
    print("  brew install bcftools")
    sys.exit(1)


def group_by_chrom(rsids: list[str]) -> dict[str, list[tuple[str, int]]]:
    """Group rsID positions by chromosome."""
    by_chrom: dict[str, list[tuple[str, int]]] = defaultdict(list)
    missing = []
    for rsid in rsids:
        if rsid in RSID_POSITIONS:
            chrom, pos = RSID_POSITIONS[rsid]
            by_chrom[chrom].append((rsid, pos))
        else:
            missing.append(rsid)
    if missing:
        print(f"  ⚠  No position mapping for: {', '.join(missing)}")
    return dict(by_chrom)


def fetch_chrom(sample: str, chrom: str, positions: list[tuple[str, int]],
                tmp_dir: str) -> Path | None:
    """Stream-fetch one chromosome's worth of positions from 1000 Genomes."""
    url = BASE_URL.format(chrom=chrom)

    # Build region string: chr1:11856378-11856378,chr1:11854476-11854476,...
    region_str = ",".join(f"chr{chrom}:{pos}-{pos}" for _, pos in positions)

    out_file = Path(tmp_dir) / f"chr{chrom}.vcf"

    cmd = [
        "bcftools", "view",
        "--samples", sample,
        "--regions", region_str,
        "--output-type", "v",      # uncompressed VCF
        "--output", str(out_file),
        url,
    ]

    print(f"  chr{chrom:>2}  {len(positions):>2} positions ... ", end="", flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FAILED")
        print(f"         {result.stderr[:200]}")
        return None

    # Count variants fetched
    n = sum(1 for line in out_file.read_text().splitlines()
            if line and not line.startswith("#"))
    print(f"OK  ({n} variants)")
    return out_file if n > 0 else None


def _pos_to_rsid_map() -> dict[tuple[str, int], str]:
    """Build a (chrom_without_chr, pos) -> rsid lookup from the position table."""
    return {(chrom, pos): rsid for rsid, (chrom, pos) in RSID_POSITIONS.items()}


def merge_vcfs(vcf_files: list[Path], sample: str, out_path: Path) -> None:
    """Merge per-chromosome VCFs, inject rsIDs, and add GRCh38 reference header."""
    pos_map     = _pos_to_rsid_map()
    header_lines = []
    variant_lines = []
    header_done  = False
    annotated    = 0

    for vcf in sorted(vcf_files, key=lambda p: p.name):
        for line in vcf.read_text().splitlines():
            if line.startswith("##"):
                if not header_done:
                    header_lines.append(line)
            elif line.startswith("#CHROM"):
                if not header_done:
                    header_lines.append(line)
                    header_done = True
            elif line:
                cols = line.split("\t")
                if len(cols) >= 3:
                    chrom_num = cols[0].replace("chr", "")   # "chr1" -> "1"
                    try:
                        pos = int(cols[1])
                    except ValueError:
                        variant_lines.append(line)
                        continue
                    # Inject rsID when the ID column is blank or "."
                    if not cols[2].startswith("rs"):
                        rsid = pos_map.get((chrom_num, pos))
                        if rsid:
                            cols[2] = rsid
                            line    = "\t".join(cols)
                            annotated += 1
                variant_lines.append(line)

    # Inject ##reference=GRCh38 so the pipeline detects the correct build
    ref_header = "##reference=GRCh38"
    insert_at  = next(
        (i for i, l in enumerate(header_lines) if l.startswith("#CHROM")),
        len(header_lines),
    )
    header_lines.insert(insert_at, ref_header)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(header_lines) + "\n")
        f.write("\n".join(variant_lines) + "\n")

    print(f"\n  Total variants: {len(variant_lines)}  |  rsIDs injected: {annotated}")


def load_whitelist_rsids(whitelist_path: str = "data/whitelist/whitelist_v0_1.csv") -> list[str]:
    """Read rsIDs from the project whitelist CSV."""
    p = Path(whitelist_path)
    if not p.exists():
        # Fall back to the hardcoded list
        return list(RSID_POSITIONS.keys())
    rsids = []
    with open(p) as f:
        for row in csv.DictReader(f):
            rsid = row.get("rsid", "").strip()
            if rsid and rsid.startswith("rs"):
                rsids.append(rsid)
    return rsids


def download_sample(sample: str, out_path: Path,
                    whitelist: str = "data/whitelist/whitelist_v0_1.csv") -> None:
    print(f"\n── Nebula: downloading {sample} from 1000 Genomes ──────────────")
    print(f"   Output:    {out_path}")
    print(f"   Reference: GRCh38 (hg38)")
    print(f"   Method:    bcftools HTTP streaming (no full genome download)\n")

    rsids = load_whitelist_rsids(whitelist)
    by_chrom = group_by_chrom(rsids)

    total_pos = sum(len(v) for v in by_chrom.values())
    chroms    = sorted(by_chrom.keys(), key=lambda x: int(x) if x.isdigit() else 99)
    print(f"  {len(rsids)} whitelist rsIDs  →  {total_pos} mapped  →  {len(chroms)} chromosomes\n")

    vcf_files: list[Path] = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        for chrom in chroms:
            f = fetch_chrom(sample, chrom, by_chrom[chrom], tmp_dir)
            if f:
                vcf_files.append(f)

        if not vcf_files:
            print("\n✗  No variants fetched. Check your internet connection and bcftools install.")
            sys.exit(1)

        print(f"\n  Merging {len(vcf_files)} chromosome files ...")
        merge_vcfs(vcf_files, sample, out_path)

    print(f"\n✓  VCF saved to: {out_path}")
    print(f"\n── Next step ─────────────────────────────────────────────────────")
    print(f"  1. Fill in the questionnaire:")
    print(f"     python scripts/questionnaire.py --sample-id {sample} --out data/meta/{sample}_meta.json")
    print(f"  2. Run the pipeline:")
    print(f"     python -m nebula.cli run --vcf {out_path} --meta data/meta/{sample}_meta.json --out out/")
    print(f"  3. Generate the PDF:")
    print(f"     python scripts/render_report.py --report out/report.json --out out/{sample}_report.pdf")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description="Download a 1000 Genomes sample VCF for Nebula")
    ap.add_argument("--sample",    default="HG00096",
                    help="1000 Genomes sample ID (default: HG00096)")
    ap.add_argument("--out",       default=None,
                    help="Output VCF path (default: data/vcf/<SAMPLE>.vcf)")
    ap.add_argument("--whitelist", default="data/whitelist/whitelist_v0_1.csv",
                    help="Path to whitelist CSV")
    ap.add_argument("--list-samples", action="store_true",
                    help="Show well-known sample IDs and exit")
    args = ap.parse_args()

    if args.list_samples:
        print("\nWell-characterised 1000 Genomes samples:")
        for sid, desc in KNOWN_SAMPLES.items():
            print(f"  {sid:<12}  {desc}")
        print()
        return

    if not check_bcftools():
        print("✗  bcftools not found.")
        install_hint()

    out = Path(args.out) if args.out else Path(f"data/vcf/{args.sample}.vcf")
    download_sample(args.sample, out, args.whitelist)


if __name__ == "__main__":
    main()
