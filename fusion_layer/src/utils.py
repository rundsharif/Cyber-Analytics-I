"""Shared utility helpers for config, outputs, and metadata persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.contracts import OUTPUT_COLUMNS
from src.risk_mapping import label_from_score, map_scores_to_risk
from src.validators import validate_output_dataframe

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "fusion_config.yaml"


def get_project_root() -> Path:
    """Return the fusion-layer project root."""

    return PROJECT_ROOT


def resolve_project_path(path_value: str | Path) -> Path:
    """Resolve a path relative to the fusion-layer root when needed."""

    candidate = Path(path_value)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load YAML configuration for the fusion layer."""

    resolved_path = resolve_project_path(config_path or DEFAULT_CONFIG_PATH)
    with resolved_path.open("r", encoding="utf-8") as file_handle:
        config = yaml.safe_load(file_handle) or {}
    return config


def ensure_parent_directory(path_value: str | Path) -> Path:
    """Create the parent directory for a file path if it does not exist."""

    path = resolve_project_path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_configured_artifact_path(config: dict[str, Any], key: str) -> Path:
    """Resolve an artifact path from the YAML config."""

    try:
        path_value = config["artifacts"][key]
    except KeyError as exc:
        raise KeyError(f"Missing artifacts.{key} in configuration.") from exc
    return resolve_project_path(path_value)


def build_output_dataframe(
    source_df: pd.DataFrame,
    scores: pd.Series,
    fusion_method: str,
    threat_threshold: float,
) -> pd.DataFrame:
    """Build and validate the final inference output dataframe."""

    score_series = pd.Series(scores, index=source_df.index, dtype=float).clip(0.0, 1.0)
    output_df = pd.DataFrame(
        {
            "email_id": source_df["email_id"].astype("string"),
            "final_score": score_series,
            "final_label": [label_from_score(score, threshold=threat_threshold) for score in score_series],
            "risk_level": map_scores_to_risk(score_series),
            "models_used": source_df["models_used"],
            "fusion_method": fusion_method,
        }
    )
    validated = validate_output_dataframe(output_df)
    return validated.loc[:, list(OUTPUT_COLUMNS)]


def save_json(payload: dict[str, Any], output_path: str | Path) -> Path:
    """Persist metadata as formatted JSON."""

    path = ensure_parent_directory(output_path)
    with path.open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2, sort_keys=True)
    return path
