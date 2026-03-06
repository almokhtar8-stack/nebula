"""
Rule loader.

Reads versioned YAML rulesets. Rules live entirely outside code —
this module only deserializes and validates them.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Required top-level fields for every rule in a YAML ruleset
REQUIRED_RULE_KEYS = {
    "id",
    "category",
    "description",
    "trigger",
    "recommendation_text",
    "reason",
    "evidence_grade",
    "base_confidence",
    "practical_action",
    "review_interval",
    "disclaimer",
    "referral_trigger",
    "output_tier",
}


class RulesetLoadError(Exception):
    """Raised when a ruleset file cannot be loaded or is malformed."""


def load_ruleset(ruleset_path: Path) -> dict[str, Any]:
    """
    Load and validate a YAML ruleset file.

    Returns the raw ruleset dict with top-level keys:
        version, description, rules (list of rule dicts)

    Raises:
        RulesetLoadError on any structural problem.
    """
    ruleset_path = Path(ruleset_path)
    if not ruleset_path.exists():
        raise RulesetLoadError(f"Ruleset file not found: {ruleset_path}")

    try:
        with ruleset_path.open("r") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise RulesetLoadError(f"YAML parse error in {ruleset_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise RulesetLoadError("Ruleset YAML must be a top-level mapping.")

    for required in ("version", "rules"):
        if required not in data:
            raise RulesetLoadError(f"Ruleset missing required top-level key: '{required}'")

    if not isinstance(data["rules"], list):
        raise RulesetLoadError("'rules' must be a list.")

    errors: list[str] = []
    rule_ids: set[str] = set()

    for i, rule in enumerate(data["rules"]):
        if not isinstance(rule, dict):
            errors.append(f"Rule [{i}] is not a dict.")
            continue

        rule_id = rule.get("id", f"<unnamed[{i}]>")

        missing = REQUIRED_RULE_KEYS - set(rule.keys())
        if missing:
            errors.append(f"Rule '{rule_id}' missing keys: {missing}")

        if rule_id in rule_ids:
            errors.append(f"Duplicate rule ID: '{rule_id}'")
        rule_ids.add(rule_id)

        # Validate confidence_adjustments structure if present
        adjustments = rule.get("confidence_adjustments", [])
        if not isinstance(adjustments, list):
            errors.append(f"Rule '{rule_id}': confidence_adjustments must be a list.")

    if errors:
        raise RulesetLoadError(
            f"Ruleset validation failed with {len(errors)} error(s):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )

    logger.info(
        "Loaded ruleset v%s with %d rules from %s",
        data["version"],
        len(data["rules"]),
        ruleset_path,
    )
    return data
