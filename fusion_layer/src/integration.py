"""Integration helpers for assembling branch-model outputs into fusion input.

This module is designed to make the fusion layer easier to plug into a live
pipeline where header, body, and malware models may produce separate outputs.
It provides:

- branch score normalization with flexible column alias support,
- duplicate email handling strategies (especially useful for attachments),
- assembly of canonical fusion input rows,
- an end-to-end runner that assembles, fuses, and writes outputs/manifests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any

import pandas as pd

from src.contracts import INFERENCE_INPUT_COLUMNS, MODEL_PROBABILITY_COLUMNS
from src.inference import SUPPORTED_FUSION_METHODS
from src.loaders import CSV_MISSING_VALUES, load_inference_dataframe_from_dataframe, write_output_dataframe
from src.logistic_fusion import LogisticFusionModel
from src.preprocess import annotate_model_availability
from src.s3_io import (
    download_s3_object_to_tempfile,
    read_csv_from_s3,
    write_dataframe_to_s3_csv,
    write_json_to_s3,
)
from src.soft_voting import SoftVotingFusion
from src.utils import ensure_parent_directory, get_project_root, load_config, resolve_project_path, save_json
from src.validators import validate_email_ids, validate_probability_columns

BRANCH_MODELS = ("header", "body", "malware")
SUPPORTED_JOIN_TYPES = ("outer", "inner")
SUPPORTED_DUPLICATE_STRATEGIES = ("error", "first", "max", "mean", "min")

BRANCH_SCORE_COLUMN_BY_MODEL = {
    "header": "p_header",
    "body": "p_body",
    "malware": "p_malware",
}

DEFAULT_EMAIL_ID_ALIASES = ("email_id", "message_id", "id")

DEFAULT_SCORE_COLUMN_ALIASES = {
    "header": (
        "p_header",
        "header_score",
        "header_probability",
        "p_header_score",
        "malicious_probability",
        "probability",
        "score",
    ),
    "body": (
        "p_body",
        "body_score",
        "body_probability",
        "p_body_score",
        "malicious_probability",
        "probability",
        "score",
    ),
    "malware": (
        "p_malware",
        "p_attachment",
        "malware_score",
        "attachment_score",
        "p_malware_score",
        "p_attachment_score",
        "attachment_probability",
        "malicious_probability",
        "probability",
        "score",
    ),
}

DEFAULT_DUPLICATE_STRATEGY_BY_MODEL = {
    "header": "error",
    "body": "error",
    "malware": "max",
}

DEFAULT_DIRECTORY_REQUIRED_MODELS = ("header", "body")
DEFAULT_PER_EMAIL_OUTPUT_FILENAME = "fusion_output.json"
DEFAULT_STATE_PATH = Path("artifacts") / "processed_emails_state.json"
SUPPORTED_SCORE_FILE_SUFFIXES = {".json", ".csv", ".txt"}
FLEXIBLE_SCORE_NAME_KEYWORDS = ("score", "scores", "prob", "probability", "prediction", "predictions", "result")
DEFAULT_DIRECTORY_SCORE_FILE_HINTS = {
    "header": ("header_score", "header_scores", "header_prediction", "header_probability", "p_header"),
    "body": ("body_score", "body_scores", "body_prediction", "body_probability", "p_body"),
    "malware": (
        "malware_score",
        "malware_scores",
        "attachment_score",
        "attachment_scores",
        "malware_prediction",
        "attachment_prediction",
        "p_malware",
        "p_attachment",
    ),
}
DEFAULT_SCORE_KEY_ALIASES = {
    "header": DEFAULT_SCORE_COLUMN_ALIASES["header"],
    "body": DEFAULT_SCORE_COLUMN_ALIASES["body"],
    "malware": DEFAULT_SCORE_COLUMN_ALIASES["malware"],
}
MODALITY_DISCOVERY_KEYWORDS = {
    "header": ("header",),
    "body": ("body",),
    "malware": ("malware", "attachment", "attachments"),
}
NUMERIC_VALUE_REGEX = re.compile(r"-?\d+(?:\.\d+)?")
BRANCH_INPUT_ENV_VAR_BY_MODEL = {
    "header": "FUSION_HEADER_INPUT",
    "body": "FUSION_BODY_INPUT",
    "malware": "FUSION_MALWARE_INPUT",
}
BRANCH_EMAIL_ID_COLUMN_ENV_VAR_BY_MODEL = {
    "header": "FUSION_HEADER_EMAIL_ID_COLUMN",
    "body": "FUSION_BODY_EMAIL_ID_COLUMN",
    "malware": "FUSION_MALWARE_EMAIL_ID_COLUMN",
}
BRANCH_SCORE_COLUMN_ENV_VAR_BY_MODEL = {
    "header": "FUSION_HEADER_SCORE_COLUMN",
    "body": "FUSION_BODY_SCORE_COLUMN",
    "malware": "FUSION_MALWARE_SCORE_COLUMN",
}


@dataclass
class IntegratedFusionResult:
    """Return value for end-to-end integrated fusion runs."""

    assembled_input: pd.DataFrame
    predictions: pd.DataFrame
    manifest: dict[str, Any]
    output_location: str | None
    assembled_input_location: str | None
    manifest_location: str | None
    state_location: str | None = None


def _is_s3_uri(path_or_uri: str | Path | None) -> bool:
    if path_or_uri is None:
        return False
    return str(path_or_uri).strip().startswith("s3://")


def _normalize_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    normalized = dataframe.copy()
    normalized.columns = [str(column).strip() for column in normalized.columns]
    return normalized


def _ensure_valid_model_name(model_name: str) -> str:
    cleaned = str(model_name).strip().lower()
    if cleaned not in BRANCH_MODELS:
        raise ValueError(f"model_name must be one of {BRANCH_MODELS}, got {model_name!r}.")
    return cleaned


def _clean_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _get_branch_source_config(integration_config: dict[str, Any], model_name: str) -> dict[str, Any]:
    sources_config = integration_config.get("sources", {})
    branch_config = sources_config.get(model_name, {}) if isinstance(sources_config, dict) else {}
    return branch_config if isinstance(branch_config, dict) else {}


def _resolve_branch_source_location(
    model_name: str,
    explicit_source: str | Path | None,
    integration_config: dict[str, Any],
) -> str | None:
    resolved_model_name = _ensure_valid_model_name(model_name)
    explicit_value = _clean_optional_string(explicit_source)
    if explicit_value is not None:
        return explicit_value

    environment_value = _clean_optional_string(os.getenv(BRANCH_INPUT_ENV_VAR_BY_MODEL[resolved_model_name]))
    if environment_value is not None:
        return environment_value

    branch_config = _get_branch_source_config(integration_config, resolved_model_name)
    return _clean_optional_string(branch_config.get("location") or branch_config.get("input"))


def _resolve_branch_column_override(
    model_name: str,
    explicit_value: str | None,
    integration_config: dict[str, Any],
    *,
    field_name: str,
    env_var_mapping: dict[str, str],
) -> str | None:
    resolved_model_name = _ensure_valid_model_name(model_name)
    cleaned_explicit_value = _clean_optional_string(explicit_value)
    if cleaned_explicit_value is not None:
        return cleaned_explicit_value

    environment_value = _clean_optional_string(os.getenv(env_var_mapping[resolved_model_name]))
    if environment_value is not None:
        return environment_value

    branch_config = _get_branch_source_config(integration_config, resolved_model_name)
    return _clean_optional_string(branch_config.get(field_name))


def _resolve_column_name(
    columns: list[str],
    explicit_name: str | None,
    aliases: tuple[str, ...],
    label: str,
) -> str:
    if explicit_name:
        cleaned = str(explicit_name).strip()
        if cleaned not in columns:
            raise ValueError(f"Explicit {label} column {cleaned!r} was not found in columns {columns}.")
        return cleaned

    for alias in aliases:
        if alias in columns:
            return alias

    raise ValueError(f"Could not infer {label}. Expected one of {aliases}, found columns {columns}.")


def _aggregate_duplicate_scores(
    dataframe: pd.DataFrame,
    model_name: str,
    probability_column: str,
    duplicate_strategy: str,
) -> pd.DataFrame:
    strategy = str(duplicate_strategy).strip().lower()
    if strategy not in SUPPORTED_DUPLICATE_STRATEGIES:
        raise ValueError(
            f"duplicate_strategy must be one of {SUPPORTED_DUPLICATE_STRATEGIES}, got {duplicate_strategy!r}."
        )

    if not dataframe["email_id"].duplicated().any():
        return dataframe

    if strategy == "error":
        duplicates = dataframe.loc[dataframe["email_id"].duplicated(keep=False), "email_id"].tolist()
        raise ValueError(
            f"{model_name} branch contains duplicate email_id values: {duplicates}. "
            "Provide a duplicate aggregation strategy such as 'max' or 'mean'."
        )

    if strategy == "first":
        return dataframe.groupby("email_id", as_index=False).first()

    aggregated = dataframe.groupby("email_id", as_index=False)[probability_column].agg(strategy)
    return aggregated


def normalize_branch_score_dataframe(
    dataframe: pd.DataFrame,
    model_name: str,
    email_id_column: str | None = None,
    score_column: str | None = None,
    duplicate_strategy: str | None = None,
) -> pd.DataFrame:
    """Normalize a branch-model score dataframe into canonical fusion columns.

    The returned dataframe always contains exactly two columns:

    - `email_id`
    - canonical model probability column (`p_header`, `p_body`, or `p_malware`)
    """

    normalized_model_name = _ensure_valid_model_name(model_name)
    canonical_score_column = BRANCH_SCORE_COLUMN_BY_MODEL[normalized_model_name]
    normalized_df = _normalize_columns(dataframe)
    columns = list(normalized_df.columns)

    resolved_email_id_column = _resolve_column_name(
        columns=columns,
        explicit_name=email_id_column,
        aliases=DEFAULT_EMAIL_ID_ALIASES,
        label=f"{normalized_model_name} email_id column",
    )
    resolved_score_column = _resolve_column_name(
        columns=columns,
        explicit_name=score_column,
        aliases=DEFAULT_SCORE_COLUMN_ALIASES[normalized_model_name],
        label=f"{normalized_model_name} score column",
    )

    branch_df = normalized_df.loc[:, [resolved_email_id_column, resolved_score_column]].copy()
    branch_df = branch_df.rename(
        columns={
            resolved_email_id_column: "email_id",
            resolved_score_column: canonical_score_column,
        }
    )
    branch_df["email_id"] = branch_df["email_id"].astype("string").str.strip()
    branch_df[canonical_score_column] = pd.to_numeric(branch_df[canonical_score_column], errors="coerce")

    resolved_duplicate_strategy = (
        duplicate_strategy or DEFAULT_DUPLICATE_STRATEGY_BY_MODEL[normalized_model_name]
    )
    branch_df = _aggregate_duplicate_scores(
        dataframe=branch_df,
        model_name=normalized_model_name,
        probability_column=canonical_score_column,
        duplicate_strategy=resolved_duplicate_strategy,
    )

    validate_email_ids(branch_df)
    validate_probability_columns(branch_df, [canonical_score_column])
    return branch_df.loc[:, ["email_id", canonical_score_column]].copy()


def assemble_fusion_input(
    header_scores: pd.DataFrame | None = None,
    body_scores: pd.DataFrame | None = None,
    malware_scores: pd.DataFrame | None = None,
    join_type: str = "outer",
) -> pd.DataFrame:
    """Merge normalized branch scoreframes into the canonical fusion input contract."""

    resolved_join_type = str(join_type).strip().lower()
    if resolved_join_type not in SUPPORTED_JOIN_TYPES:
        raise ValueError(f"join_type must be one of {SUPPORTED_JOIN_TYPES}, got {join_type!r}.")

    frames = [
        frame.loc[:, ["email_id", "p_header"]].copy() for frame in [header_scores] if frame is not None
    ]
    frames += [
        frame.loc[:, ["email_id", "p_body"]].copy() for frame in [body_scores] if frame is not None
    ]
    frames += [
        frame.loc[:, ["email_id", "p_malware"]].copy() for frame in [malware_scores] if frame is not None
    ]

    if not frames:
        raise ValueError("At least one branch score dataframe must be provided for assembly.")

    assembled = frames[0]
    for frame in frames[1:]:
        assembled = assembled.merge(frame, on="email_id", how=resolved_join_type)

    for column in MODEL_PROBABILITY_COLUMNS:
        if column not in assembled.columns:
            assembled[column] = pd.NA

    assembled = assembled.loc[:, list(INFERENCE_INPUT_COLUMNS)].copy()
    return load_inference_dataframe_from_dataframe(assembled)


def _ensure_s3_client(s3_client: Any | None) -> Any:
    if s3_client is not None:
        return s3_client

    try:
        import boto3  # type: ignore
    except ImportError as exc:  # pragma: no cover - runtime dependent
        raise ImportError("boto3 is required when using S3 integration sources or destinations.") from exc

    return boto3.client("s3")


def _read_local_csv(path_value: str | Path) -> pd.DataFrame:
    resolved_path = resolve_project_path(path_value)
    if not resolved_path.exists():
        raise FileNotFoundError(f"CSV file not found: {resolved_path}")
    return pd.read_csv(
        resolved_path,
        keep_default_na=True,
        na_values=CSV_MISSING_VALUES,
    )


def load_branch_score_dataframe(
    source: str | Path | None,
    model_name: str,
    email_id_column: str | None = None,
    score_column: str | None = None,
    duplicate_strategy: str | None = None,
    s3_client: Any | None = None,
) -> pd.DataFrame | None:
    """Load a branch-model score CSV from local disk or S3 and normalize it."""

    if source is None or str(source).strip() == "":
        return None

    if _is_s3_uri(source):
        raw_df = read_csv_from_s3(str(source), _ensure_s3_client(s3_client))
    else:
        raw_df = _read_local_csv(source)

    return normalize_branch_score_dataframe(
        raw_df,
        model_name=model_name,
        email_id_column=email_id_column,
        score_column=score_column,
        duplicate_strategy=duplicate_strategy,
    )


def _resolve_fusion_method(fusion_method: str | None, config: dict[str, Any]) -> str:
    method = fusion_method or config.get("fusion", {}).get("primary_method", "logistic_regression_stacking")
    method = str(method).strip()
    if method not in SUPPORTED_FUSION_METHODS:
        raise ValueError(f"fusion_method must be one of {SUPPORTED_FUSION_METHODS}, got {method!r}.")
    return method


def _get_integration_outputs_config(integration_config: dict[str, Any]) -> dict[str, Any]:
    outputs_config = integration_config.get("outputs", {})
    return outputs_config if isinstance(outputs_config, dict) else {}


def _resolve_configured_output_destination(
    explicit_destination: str | Path | None,
    integration_config: dict[str, Any],
    *,
    config_keys: tuple[str, ...],
) -> str | Path | None:
    if explicit_destination is not None:
        return explicit_destination

    outputs_config = _get_integration_outputs_config(integration_config)
    for config_key in config_keys:
        configured_value = _clean_optional_string(outputs_config.get(config_key))
        if configured_value is not None:
            return configured_value
    return None


def _resolve_output_destination(
    output_path: str | Path | None,
    method: str,
    integration_config: dict[str, Any],
) -> str | Path:
    configured_output_destination = _resolve_configured_output_destination(
        output_path,
        integration_config,
        config_keys=("predictions", "output", "output_path"),
    )
    if configured_output_destination is not None:
        return configured_output_destination
    return get_project_root() / "artifacts" / f"integrated_{method}_predictions.csv"


def _default_local_manifest_path(output_destination: str | Path) -> Path:
    resolved_output = resolve_project_path(output_destination)
    return resolved_output.with_name(f"{resolved_output.stem}_manifest.json")


def _write_dataframe_destination(
    dataframe: pd.DataFrame,
    destination: str | Path,
    s3_client: Any | None = None,
    validate_as_output: bool = False,
) -> str:
    if _is_s3_uri(destination):
        write_dataframe_to_s3_csv(dataframe, str(destination), _ensure_s3_client(s3_client))
        return str(destination)

    if validate_as_output:
        output_path = write_output_dataframe(dataframe, destination)
    else:
        output_path = ensure_parent_directory(destination)
        dataframe.to_csv(output_path, index=False)
    return str(output_path)


def _write_json_destination(
    payload: dict[str, Any],
    destination: str | Path,
    s3_client: Any | None = None,
) -> str:
    if _is_s3_uri(destination):
        write_json_to_s3(payload, str(destination), _ensure_s3_client(s3_client))
        return str(destination)

    output_path = save_json(payload, destination)
    return str(output_path)


def _resolve_model_artifact_location(
    model_artifact: str | Path | None,
    config: dict[str, Any],
) -> str:
    if model_artifact is not None:
        return str(model_artifact)
    configured_path = config.get("artifacts", {}).get("model_path")
    if not configured_path:
        raise ValueError("Missing artifacts.model_path in config and no model_artifact override was provided.")
    return str(configured_path)


def _run_fusion_predictions(
    assembled_input: pd.DataFrame,
    fusion_method: str,
    config: dict[str, Any],
    model_artifact: str | Path | None,
    s3_client: Any | None,
) -> pd.DataFrame:
    threat_threshold = float(config.get("thresholds", {}).get("final_label", 0.50))

    if fusion_method == "soft_voting":
        engine = SoftVotingFusion(threat_threshold=threat_threshold)
        return engine.predict(assembled_input)

    artifact_location = _resolve_model_artifact_location(model_artifact, config)
    if _is_s3_uri(artifact_location):
        resolved_artifact_path = download_s3_object_to_tempfile(
            str(artifact_location),
            _ensure_s3_client(s3_client),
            suffix=".joblib",
        )
    else:
        resolved_artifact_path = resolve_project_path(artifact_location)

    engine = LogisticFusionModel.load(resolved_artifact_path)
    return engine.predict(assembled_input)


def build_integration_manifest(
    assembled_input: pd.DataFrame,
    predictions: pd.DataFrame,
    fusion_method: str,
    join_type: str,
    sources: dict[str, str | None],
    duplicate_strategies: dict[str, str],
) -> dict[str, Any]:
    """Build an audit-friendly manifest for an integrated fusion run."""

    annotated = annotate_model_availability(assembled_input)
    risk_distribution = {
        str(key): int(value)
        for key, value in predictions["risk_level"].value_counts(dropna=False).sort_index().items()
    }
    label_distribution = {
        str(key): int(value)
        for key, value in predictions["final_label"].value_counts(dropna=False).sort_index().items()
    }

    return {
        "input_mode": "assembled_branch_scores",
        "fusion_method": fusion_method,
        "join_type": join_type,
        "rows_scored": int(len(predictions)),
        "sources": sources,
        "duplicate_strategies": duplicate_strategies,
        "coverage": {
            "rows_with_header": int(annotated["has_header"].sum()),
            "rows_with_body": int(annotated["has_body"].sum()),
            "rows_with_malware": int(annotated["has_malware"].sum()),
            "rows_with_all_three": int((annotated["models_present_count"] == 3).sum()),
            "rows_missing_any_modality": int((annotated["models_present_count"] < 3).sum()),
        },
        "label_distribution": label_distribution,
        "risk_distribution": risk_distribution,
        "output_columns": list(predictions.columns),
    }


def run_integrated_fusion(
    *,
    header_input: str | Path | None = None,
    body_input: str | Path | None = None,
    malware_input: str | Path | None = None,
    fusion_method: str | None = None,
    output_path: str | Path | None = None,
    assembled_input_output: str | Path | None = None,
    manifest_output: str | Path | None = None,
    config_path: str | Path | None = None,
    model_artifact: str | Path | None = None,
    header_email_id_column: str | None = None,
    header_score_column: str | None = None,
    body_email_id_column: str | None = None,
    body_score_column: str | None = None,
    malware_email_id_column: str | None = None,
    malware_score_column: str | None = None,
    header_duplicate_strategy: str | None = None,
    body_duplicate_strategy: str | None = None,
    malware_duplicate_strategy: str | None = None,
    join_type: str | None = None,
    s3_client: Any | None = None,
) -> IntegratedFusionResult:
    """Assemble branch scores, run fusion, and persist integration artifacts."""

    config = load_config(config_path)
    method = _resolve_fusion_method(fusion_method, config)
    integration_config = config.get("integration", {})
    resolved_header_input = _resolve_branch_source_location("header", header_input, integration_config)
    resolved_body_input = _resolve_branch_source_location("body", body_input, integration_config)
    resolved_malware_input = _resolve_branch_source_location("malware", malware_input, integration_config)

    if not any([resolved_header_input, resolved_body_input, resolved_malware_input]):
        raise ValueError(
            "No branch input sources were resolved. Provide --header-input/--body-input/--malware-input, "
            "set FUSION_HEADER_INPUT/FUSION_BODY_INPUT/FUSION_MALWARE_INPUT, or configure "
            "integration.sources.<model>.location in fusion_config.yaml."
        )

    resolved_header_email_id_column = _resolve_branch_column_override(
        "header",
        header_email_id_column,
        integration_config,
        field_name="email_id_column",
        env_var_mapping=BRANCH_EMAIL_ID_COLUMN_ENV_VAR_BY_MODEL,
    )
    resolved_body_email_id_column = _resolve_branch_column_override(
        "body",
        body_email_id_column,
        integration_config,
        field_name="email_id_column",
        env_var_mapping=BRANCH_EMAIL_ID_COLUMN_ENV_VAR_BY_MODEL,
    )
    resolved_malware_email_id_column = _resolve_branch_column_override(
        "malware",
        malware_email_id_column,
        integration_config,
        field_name="email_id_column",
        env_var_mapping=BRANCH_EMAIL_ID_COLUMN_ENV_VAR_BY_MODEL,
    )
    resolved_header_score_column = _resolve_branch_column_override(
        "header",
        header_score_column,
        integration_config,
        field_name="score_column",
        env_var_mapping=BRANCH_SCORE_COLUMN_ENV_VAR_BY_MODEL,
    )
    resolved_body_score_column = _resolve_branch_column_override(
        "body",
        body_score_column,
        integration_config,
        field_name="score_column",
        env_var_mapping=BRANCH_SCORE_COLUMN_ENV_VAR_BY_MODEL,
    )
    resolved_malware_score_column = _resolve_branch_column_override(
        "malware",
        malware_score_column,
        integration_config,
        field_name="score_column",
        env_var_mapping=BRANCH_SCORE_COLUMN_ENV_VAR_BY_MODEL,
    )

    resolved_join_type = str(join_type or integration_config.get("join_type", "outer")).strip().lower()
    if resolved_join_type not in SUPPORTED_JOIN_TYPES:
        raise ValueError(f"join_type must be one of {SUPPORTED_JOIN_TYPES}, got {join_type!r}.")

    resolved_header_duplicate_strategy = (
        header_duplicate_strategy
        or integration_config.get("duplicate_strategy", {}).get("header")
        or DEFAULT_DUPLICATE_STRATEGY_BY_MODEL["header"]
    )
    resolved_body_duplicate_strategy = (
        body_duplicate_strategy
        or integration_config.get("duplicate_strategy", {}).get("body")
        or DEFAULT_DUPLICATE_STRATEGY_BY_MODEL["body"]
    )
    resolved_malware_duplicate_strategy = (
        malware_duplicate_strategy
        or integration_config.get("duplicate_strategy", {}).get("malware")
        or DEFAULT_DUPLICATE_STRATEGY_BY_MODEL["malware"]
    )

    header_scores = load_branch_score_dataframe(
        resolved_header_input,
        model_name="header",
        email_id_column=resolved_header_email_id_column,
        score_column=resolved_header_score_column,
        duplicate_strategy=resolved_header_duplicate_strategy,
        s3_client=s3_client,
    )
    body_scores = load_branch_score_dataframe(
        resolved_body_input,
        model_name="body",
        email_id_column=resolved_body_email_id_column,
        score_column=resolved_body_score_column,
        duplicate_strategy=resolved_body_duplicate_strategy,
        s3_client=s3_client,
    )
    malware_scores = load_branch_score_dataframe(
        resolved_malware_input,
        model_name="malware",
        email_id_column=resolved_malware_email_id_column,
        score_column=resolved_malware_score_column,
        duplicate_strategy=resolved_malware_duplicate_strategy,
        s3_client=s3_client,
    )

    assembled_input = assemble_fusion_input(
        header_scores=header_scores,
        body_scores=body_scores,
        malware_scores=malware_scores,
        join_type=resolved_join_type,
    )
    predictions = _run_fusion_predictions(
        assembled_input=assembled_input,
        fusion_method=method,
        config=config,
        model_artifact=model_artifact,
        s3_client=s3_client,
    )

    resolved_output_destination = _resolve_output_destination(output_path, method, integration_config)
    output_location = _write_dataframe_destination(
        predictions,
        resolved_output_destination,
        s3_client=s3_client,
        validate_as_output=not _is_s3_uri(resolved_output_destination),
    )

    resolved_assembled_input_destination = _resolve_configured_output_destination(
        assembled_input_output,
        integration_config,
        config_keys=("assembled_input", "assembled_input_output"),
    )
    assembled_input_location: str | None = None
    if resolved_assembled_input_destination is not None:
        assembled_input_location = _write_dataframe_destination(
            assembled_input,
            resolved_assembled_input_destination,
            s3_client=s3_client,
            validate_as_output=False,
        )

    resolved_manifest_destination = _resolve_configured_output_destination(
        manifest_output,
        integration_config,
        config_keys=("manifest", "manifest_output"),
    )
    if resolved_manifest_destination is None and not _is_s3_uri(resolved_output_destination):
        resolved_manifest_destination = _default_local_manifest_path(resolved_output_destination)

    manifest = build_integration_manifest(
        assembled_input=assembled_input,
        predictions=predictions,
        fusion_method=method,
        join_type=resolved_join_type,
        sources={
            "header": resolved_header_input,
            "body": resolved_body_input,
            "malware": resolved_malware_input,
        },
        duplicate_strategies={
            "header": resolved_header_duplicate_strategy,
            "body": resolved_body_duplicate_strategy,
            "malware": resolved_malware_duplicate_strategy,
        },
    )

    manifest_location: str | None = None
    if resolved_manifest_destination is not None:
        manifest_location = _write_json_destination(
            manifest,
            resolved_manifest_destination,
            s3_client=s3_client,
        )

    return IntegratedFusionResult(
        assembled_input=assembled_input,
        predictions=predictions,
        manifest=manifest,
        output_location=output_location,
        assembled_input_location=assembled_input_location,
        manifest_location=manifest_location,
    )