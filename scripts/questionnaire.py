#!/usr/bin/env python3
"""
scripts/questionnaire.py — Nebula lifestyle questionnaire
─────────────────────────────────────────────────────────
Guides the user through all sections and saves a meta.json
that the pipeline accepts directly via --meta.

Usage:
    python scripts/questionnaire.py
    python scripts/questionnaire.py --sample-id SAMPLE_001 --out data/meta/SAMPLE_001_meta.json
    python scripts/questionnaire.py --edit data/meta/SAMPLE_001_meta.json   # re-open existing
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# ── Terminal colours ──────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
TEAL   = "\033[36m"
GREEN  = "\033[32m"
AMBER  = "\033[33m"
RED    = "\033[31m"
WHITE  = "\033[97m"
NAVY   = "\033[34m"

def c(text, *codes): return "".join(codes) + str(text) + RESET
def header(text):    print(f"\n{c('  ' + text + '  ', BOLD, TEAL, '\033[7m')}\n")
def section(text):   print(f"\n{c('── ' + text + ' ', BOLD, NAVY)}{'─'*max(0,50-len(text))}")
def hint(text):      print(f"  {c(text, DIM)}")
def ok(text):        print(f"  {c('✓ ' + text, GREEN)}")
def warn(text):      print(f"  {c('⚠ ' + text, AMBER)}")
def err(text):       print(f"  {c('✗ ' + text, RED)}")
def q(text):         return f"  {c('?', BOLD, TEAL)} {c(text, WHITE)}: "

# ── Input helpers ─────────────────────────────────────────────────────────────
def ask(prompt: str, default: str = "") -> str:
    suffix = f"  {c('[' + default + ']', DIM)}" if default else ""
    try:
        val = input(q(prompt) + suffix + " ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\nQuestionnaire cancelled.")
        sys.exit(0)
    return val if val else default

def ask_int(prompt: str, lo: int, hi: int, default: int | None = None) -> int:
    dflt_str = str(default) if default is not None else ""
    while True:
        raw = ask(f"{prompt} ({lo}–{hi})", dflt_str)
        try:
            v = int(raw)
            if lo <= v <= hi:
                return v
            err(f"Please enter a number between {lo} and {hi}.")
        except ValueError:
            err("Please enter a whole number.")

def ask_float(prompt: str, lo: float, hi: float, default: float | None = None) -> float:
    dflt_str = str(default) if default is not None else ""
    while True:
        raw = ask(f"{prompt} ({lo}–{hi})", dflt_str)
        try:
            v = float(raw)
            if lo <= v <= hi:
                return v
            err(f"Please enter a number between {lo} and {hi}.")
        except ValueError:
            err("Please enter a number (e.g. 7.5).")

def ask_choice(prompt: str, options: list[tuple[str, str]], default: str = "") -> str:
    """Single choice from a numbered list. options = [(value, label), ...]"""
    for i, (val, label) in enumerate(options, 1):
        marker = c(f"  {i}.", BOLD, TEAL)
        active = c(f" ← default", DIM) if val == default else ""
        print(f"{marker} {label}{active}")
    dflt_idx = next((str(i) for i,(v,_) in enumerate(options,1) if v==default), "")
    while True:
        raw = ask(prompt, dflt_idx)
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
            err(f"Enter a number between 1 and {len(options)}.")
        except ValueError:
            err("Enter the number of your choice.")

def ask_multi(prompt: str, options: list[tuple[str, str]], defaults: list[str] | None = None) -> list[str]:
    """Multi-select. options = [(value, label), ...]"""
    defaults = defaults or []
    for i, (val, label) in enumerate(options, 1):
        active = c(" ← selected", DIM) if val in defaults else ""
        print(f"  {c(str(i)+'.', BOLD, TEAL)} {label}{active}")
    hint("Enter numbers separated by spaces (e.g. 1 3 4), or press Enter to keep defaults.")
    dflt_str = " ".join(str(i) for i,(v,_) in enumerate(options,1) if v in defaults)
    while True:
        raw = ask(prompt, dflt_str)
        if not raw:
            return defaults
        try:
            selected = []
            for part in raw.split():
                idx = int(part) - 1
                if 0 <= idx < len(options):
                    selected.append(options[idx][0])
                else:
                    raise ValueError(f"No option {part}")
            return selected
        except ValueError as e:
            err(f"Invalid selection: {e}. Try again.")

def ask_bool(prompt: str, default: bool = False) -> bool:
    dflt = "y" if default else "n"
    while True:
        raw = ask(f"{prompt} (y/n)", dflt).lower()
        if raw in ("y","yes","1","true"):  return True
        if raw in ("n","no","0","false"): return False
        err("Enter y or n.")

def ask_list(prompt: str, hint_text: str = "") -> list[str]:
    """Free-text comma-separated list."""
    if hint_text: hint(hint_text)
    raw = ask(prompt, "")
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]

# ── Sections ──────────────────────────────────────────────────────────────────
def section_profile(existing: dict) -> dict:
    section("Basic Profile")
    hint("This information personalises your genetic risk context.")

    age = ask_int("Age", 18, 120, existing.get("age", 30))

    sex_opts = [
        ("male",              "Male"),
        ("female",            "Female"),
        ("prefer_not_to_say", "Prefer not to say"),
    ]
    sex = ask_choice("Biological sex", sex_opts, existing.get("sex_biological","male"))

    height_cm = ask_float("Height (cm)", 100, 250, existing.get("height_cm", 175.0))
    weight_kg = ask_float("Weight (kg)",  30, 300, existing.get("weight_kg",  75.0))
    bmi = round(weight_kg / ((height_cm / 100) ** 2), 1)
    ok(f"BMI calculated: {bmi}")

    return {
        "age": age,
        "sex_biological": sex,
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "bmi": bmi,
    }


def section_fitness(existing: dict) -> dict:
    section("Exercise & Fitness")

    goal_opts = [
        ("endurance",         "Endurance (running, cycling, swimming)"),
        ("strength",          "Strength (weightlifting, resistance training)"),
        ("power",             "Power / explosiveness (HIIT, sprinting, sport)"),
        ("fat_loss",          "Fat loss and body composition"),
        ("general_wellness",  "General wellness and staying active"),
        ("sleep_optimization","Sleep and recovery optimisation"),
    ]
    goals = ask_multi("Exercise goals", goal_opts, existing.get("exercise_goals",[]))

    freq = ask_int("Training sessions per week", 0, 14, existing.get("training_frequency_per_week", 3))

    hint("Examples: running, weights, yoga, swimming, cycling, football")
    types = ask_list("Exercise types (comma-separated)", "")
    if not types:
        types = existing.get("exercise_types", [])

    injury = ask_bool("Do you have a history of tendon/ligament injuries?",
                      existing.get("injury_history", False))

    return {
        "exercise_goals": goals,
        "training_frequency_per_week": freq,
        "exercise_types": types,
        "injury_history": injury,
    }


def section_nutrition(existing: dict) -> dict:
    section("Diet & Nutrition")

    diet_opts = [
        ("omnivore",   "Omnivore (eat everything)"),
        ("vegetarian", "Vegetarian"),
        ("vegan",      "Vegan"),
        ("keto",       "Ketogenic"),
        ("paleo",      "Paleo"),
        ("other",      "Other"),
    ]
    diet = ask_choice("Dietary pattern", diet_opts, existing.get("diet_type","omnivore"))

    caffeine = ask_int("Daily caffeine intake (mg) — coffee ≈ 80mg, espresso ≈ 60mg",
                       0, 2000, existing.get("caffeine_mg_per_day", 100))

    alcohol = ask_int("Alcoholic drinks per week (1 drink = 1 beer / small wine / 1 shot)",
                      0, 100, existing.get("alcohol_drinks_per_week", 0))

    dairy = ask_bool("Do you regularly consume dairy products?",
                     existing.get("dairy_intake", True))

    sun = ask_float("Average sun exposure (hours per day)", 0, 16,
                    existing.get("sun_exposure_hours_per_day", 1.0))

    hint("Examples: vitamin D, omega-3, magnesium, B12, iron, protein powder")
    supps = ask_list("Current supplements (comma-separated, or press Enter for none)")
    if not supps:
        supps = existing.get("supplement_use", [])

    gi = ask_bool("Do you regularly experience GI symptoms (bloating, cramps, diarrhoea)?",
                  existing.get("gi_symptoms", False))
    gi_types = []
    if gi:
        hint("Examples: bloating, diarrhoea, cramping, reflux, constipation")
        gi_types = ask_list("Which GI symptoms?")
        if not gi_types:
            gi_types = existing.get("gi_symptom_types", [])

    return {
        "diet_type": diet,
        "caffeine_mg_per_day": caffeine,
        "alcohol_drinks_per_week": alcohol,
        "dairy_intake": dairy,
        "sun_exposure_hours_per_day": sun,
        "supplement_use": supps,
        "gi_symptoms": gi,
        "gi_symptom_types": gi_types,
    }


def section_sleep(existing: dict) -> dict:
    section("Sleep & Recovery")

    quality_opts = [
        ("good", "Good — I fall asleep easily and wake refreshed"),
        ("fair", "Fair — occasional trouble or unrefreshed mornings"),
        ("poor", "Poor — frequent difficulty sleeping or chronic fatigue"),
    ]
    quality = ask_choice("Overall sleep quality", quality_opts,
                         existing.get("sleep_quality","good"))

    hours = ask_float("Average sleep hours per night", 2.0, 14.0,
                      existing.get("sleep_hours_per_night", 7.5))

    early = ask_bool("Does your schedule require waking before 6:30am most days?",
                     existing.get("schedule_requires_early_wake", False))

    insomnia = ask_bool("Do you experience persistent insomnia (difficulty staying asleep 3+ nights/week)?",
                        existing.get("persistent_insomnia", False))

    return {
        "sleep_quality": quality,
        "sleep_hours_per_night": hours,
        "schedule_requires_early_wake": early,
        "persistent_insomnia": insomnia,
    }


def section_medical(existing: dict) -> dict:
    section("Medical History & Medications")
    hint("This helps contextualise pharmacogenomic and health-risk findings.")

    statins    = ask_bool("Are you currently taking statins (e.g. atorvastatin, rosuvastatin)?",
                          existing.get("currently_on_statins", False))
    pregnancy  = ask_bool("Are you currently pregnant or planning pregnancy in the next 12 months?",
                          existing.get("pregnancy_planning", False))

    hint("Examples: warfarin, clopidogrel, antidepressants, proton pump inhibitors")
    meds = ask_list("Other regular medications (comma-separated, or press Enter to skip)")
    if not meds:
        meds = existing.get("current_medications", [])

    hint("Examples: hypertension, type 2 diabetes, autoimmune condition, anxiety")
    conditions = ask_list("Diagnosed medical conditions (comma-separated, or press Enter to skip)")
    if not conditions:
        conditions = existing.get("diagnosed_conditions", [])

    return {
        "currently_on_statins": statins,
        "pregnancy_planning":   pregnancy,
        "current_medications":  meds,
        "diagnosed_conditions": conditions,
    }


def section_family_history(existing: dict) -> dict:
    section("Family History")
    hint("First-degree relatives = parents, siblings, children.")

    cvd    = ask_bool("Family history of cardiovascular disease (heart attack, stroke) before age 60?",
                      existing.get("family_history_cvd", False))
    t2d    = ask_bool("Family history of type 2 diabetes?",
                      existing.get("family_history_diabetes", False))
    brca   = ask_bool("Family history of breast or ovarian cancer?",
                      existing.get("family_history_breast_cancer", False))
    colon  = ask_bool("Family history of colorectal cancer?",
                      existing.get("family_history_colorectal_cancer", False))
    hemo   = ask_bool("Family history of iron overload / haemochromatosis?",
                      existing.get("family_history_haemochromatosis", False))

    return {
        "family_history_cvd":                cvd,
        "family_history_diabetes":           t2d,
        "family_history_breast_cancer":      brca,
        "family_history_colorectal_cancer":  colon,
        "family_history_haemochromatosis":   hemo,
    }


def section_goals(existing: dict) -> dict:
    section("Personal Health Goals")
    hint("Tell us what you most want to get out of this report.")
    hint("Examples: optimise training, understand nutrition needs, check disease risk, improve sleep")
    goals = ask_list("Your top health goals (comma-separated)")
    if not goals:
        goals = existing.get("goals", [])
    return {"goals": goals}


# ── Summary + confirm ─────────────────────────────────────────────────────────
def print_summary(meta: dict) -> None:
    section("Summary")
    fields = [
        ("Sample ID",             meta.get("sample_id")),
        ("Age / Sex",             f"{meta.get('age')} / {meta.get('sex_biological')}"),
        ("Height / Weight / BMI", f"{meta.get('height_cm')}cm / {meta.get('weight_kg')}kg / BMI {meta.get('bmi')}"),
        ("Exercise goals",        ", ".join(meta.get("exercise_goals",[]))),
        ("Training frequency",    f"{meta.get('training_frequency_per_week')} sessions/week"),
        ("Diet",                  meta.get("diet_type")),
        ("Caffeine / Alcohol",    f"{meta.get('caffeine_mg_per_day')}mg/day  |  {meta.get('alcohol_drinks_per_week')} drinks/week"),
        ("Sleep",                 f"{meta.get('sleep_hours_per_night')}h / {meta.get('sleep_quality')}"),
        ("Statins",               "Yes" if meta.get("currently_on_statins") else "No"),
        ("Family history CVD",    "Yes" if meta.get("family_history_cvd") else "No"),
        ("Family history T2D",    "Yes" if meta.get("family_history_diabetes") else "No"),
    ]
    col = 26
    for label, value in fields:
        print(f"  {c(label.ljust(col), BOLD, TEAL)}  {value}")


# ── Main ──────────────────────────────────────────────────────────────────────
def run_questionnaire(sample_id: str, out_path: Path, existing: dict) -> dict:
    header("NEBULA  ·  HEALTH QUESTIONNAIRE")
    print(f"  This questionnaire takes approximately {c('5–8 minutes', BOLD)}.")
    print(f"  Your answers are saved locally and used only to personalise your genetic report.")
    print(f"  Press {c('Ctrl+C', DIM)} at any time to cancel without saving.\n")

    meta: dict = {"sample_id": sample_id}
    meta.update(section_profile(existing))
    meta.update(section_fitness(existing))
    meta.update(section_nutrition(existing))
    meta.update(section_sleep(existing))
    meta.update(section_medical(existing))
    meta.update(section_family_history(existing))
    meta.update(section_goals(existing))
    meta["questionnaire_completed_at"] = datetime.utcnow().isoformat() + "Z"

    print_summary(meta)

    print()
    save = ask_bool("Save and continue?", True)
    if not save:
        warn("Questionnaire not saved.")
        sys.exit(0)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(meta, f, indent=2)

    ok(f"Saved to {out_path}")
    print()
    print(f"  {c('Next step:', BOLD)} run the pipeline:")
    print(f"  {c(f'python -m nebula.cli run --vcf <your.vcf> --meta {out_path} --out out/', DIM)}")
    print()
    return meta


def main():
    ap = argparse.ArgumentParser(description="Nebula lifestyle questionnaire")
    ap.add_argument("--sample-id", default=None,
                    help="Sample ID (default: prompted)")
    ap.add_argument("--out", default=None,
                    help="Output JSON path (default: data/meta/<SAMPLE_ID>_meta.json)")
    ap.add_argument("--edit", default=None, metavar="META_JSON",
                    help="Re-open and edit an existing meta.json")
    args = ap.parse_args()

    # Load existing if editing
    existing: dict = {}
    if args.edit:
        p = Path(args.edit)
        if not p.exists():
            err(f"File not found: {p}")
            sys.exit(1)
        with open(p) as f:
            existing = json.load(f)
        ok(f"Loaded existing questionnaire: {p}")

    # Sample ID
    if args.sample_id:
        sample_id = args.sample_id
    elif existing.get("sample_id"):
        sample_id = existing["sample_id"]
    else:
        sample_id = ask("Sample ID (e.g. SAMPLE_001 or your name)", "SAMPLE_001")

    # Output path
    if args.out:
        out_path = Path(args.out)
    elif args.edit:
        out_path = Path(args.edit)
    else:
        out_path = Path(f"data/meta/{sample_id}_meta.json")

    run_questionnaire(sample_id, out_path, existing)


if __name__ == "__main__":
    main()
