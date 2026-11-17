"""General utilities for project configuration, path resolution, and timestamp parsing."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import yaml


def get_project_root() -> Path:
    """Return the absolute path to the project root directory."""
    return Path(__file__).resolve().parent.parent


def load_settings(config_path: Path | str | None = None) -> Dict[str, Any]:
    """Load configuration from config/settings.yaml or a specified path."""
    if config_path is None:
        config_path = get_project_root() / "config" / "settings.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        settings = yaml.safe_load(f)
    return settings


def ensure_directories(settings: Dict[str, Any] | None = None) -> None:
    """Ensure all required project directories exist."""
    root = get_project_root()
    if settings is None:
        settings = load_settings()

    paths_cfg = settings.get("paths", {})
    for path_key in ("raw_dir", "processed_dir", "parquet_dir", "reports_dir"):
        rel_path = paths_cfg.get(path_key)
        if rel_path:
            target = root / rel_path
            target.mkdir(parents=True, exist_ok=True)


def format_iso_z(dt: datetime) -> str:
    """Format a datetime as ISO 8601 UTC with 'Z' suffix."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_z(ts_str: str) -> datetime:
    """Parse an ISO 8601 timestamp string (e.g., '2026-10-26T06:00:00Z') into UTC datetime."""
    clean_ts = ts_str.strip()
    if clean_ts.endswith("Z"):
        clean_ts = clean_ts[:-1] + "+00:00"
    return datetime.fromisoformat(clean_ts).astimezone(timezone.utc)
