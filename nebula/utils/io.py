"""
I/O utilities: writing JSON reports, creating output directories.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def write_json(data: Any, path: Path, indent: int = 2) -> None:
    """Write a JSON-serialisable object to a file, creating parents if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        json.dump(data, fh, indent=indent, default=str)
    logger.info("Wrote report to %s", path)
