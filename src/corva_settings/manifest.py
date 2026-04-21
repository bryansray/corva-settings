from __future__ import annotations

import json
from pathlib import Path


def load_app_key_from_manifest(
    manifest_path: str | Path = "manifest.json",
    *,
    fallback_app_key: str | None = None,
) -> str:
    """Load ``application.key`` from a Corva app manifest."""

    resolved_path = Path(manifest_path)
    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if fallback_app_key is not None:
            return fallback_app_key
        raise
    app_key = payload.get("application", {}).get("key")
    if not isinstance(app_key, str) or not app_key:
        raise ValueError(f"manifest application.key missing or invalid in {resolved_path}")
    return app_key
