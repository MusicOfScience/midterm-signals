#!/usr/bin/env python3
"""Safe production entry point for contextual enrichment.

`enrich_outputs` deliberately keeps the heavy adapter implementation separate
from the forecast model. The history directory also contains derivative JSON
(`index.json` and `race-series.json`) that are not forecast snapshots. This
entry point makes those files unreadable to the enrichment module so its
previous-snapshot lookup can only select a real immutable forecast snapshot.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import enrich_outputs as enrichment

DERIVATIVE_HISTORY_FILES = {"index.json", "race-series.json"}
_original_load_json = enrichment.load_json


def safe_load_json(path: Path, default: Any = None) -> Any:
    if path.parent.name == "history" and path.name in DERIVATIVE_HISTORY_FILES:
        return default
    value = _original_load_json(path, default)
    if path.parent.name == "history" and path.suffix == ".json":
        if not (
            isinstance(value, dict)
            and isinstance(value.get("races"), list)
            and value.get("generated_at")
        ):
            return default
    return value


def main() -> None:
    enrichment.load_json = safe_load_json
    enrichment.main()


if __name__ == "__main__":
    main()
