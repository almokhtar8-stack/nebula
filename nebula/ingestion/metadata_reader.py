"""
Metadata / questionnaire ingestion.

Reads a structured JSON file and validates it against the UserMetadata schema.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import ValidationError

from nebula.schemas import UserMetadata

logger = logging.getLogger(__name__)


def load_metadata(meta_path: Path) -> UserMetadata:
    """
    Load and validate a questionnaire/metadata JSON file.

    Raises:
        FileNotFoundError: if the file doesn't exist.
        ValueError: if JSON is malformed or schema validation fails.
    """
    meta_path = Path(meta_path)
    if not meta_path.exists():
        raise FileNotFoundError(f"Metadata file not found: {meta_path}")

    try:
        with meta_path.open("r") as fh:
            raw = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Metadata JSON is malformed: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("Metadata JSON must be a top-level object (dict).")

    try:
        metadata = UserMetadata.model_validate(raw)
    except ValidationError as exc:
        # Surface pydantic errors clearly
        errors = "; ".join(
            f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        raise ValueError(f"Metadata validation failed: {errors}") from exc

    logger.info("Loaded metadata for sample_id=%s", metadata.sample_id)
    return metadata
