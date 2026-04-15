"""Local processed_emails directory integration helpers.

This module is intended for the DAC/local-workstation integration path where
emails arrive in a local `processed_emails/` directory, each email has its own
UUID directory, and branch artifacts/scores live inside that directory.

The implementation is intentionally flexible because exact filenames and nested
layouts may vary during integration. The code tries to discover score files for
header/body/malware branches, parse them from JSON/CSV/TXT, skip incomplete
email directories, and optionally maintain a local state file so repeated runs
only process new or changed emails.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

import pandas as pd

from src.contracts import INFERENCE_INPUT_COLUMNS, OUTPUT_COLUMNS
from src.integration import (
    BRANCH_MODELS,
    BRANCH_SCORE_COLUMN_BY_MODEL,
    DEFAULT_DIRECTORY_REQUIRED_MODELS,
    DEFAULT_DIRECTORY_SCORE_FILE_HINTS,
    DEFAULT_EMAIL_ID_ALIASES,
    DEFAULT_PER_EMAIL_OUTPUT_FILENAME,
    DEFAULT_SCORE_KEY_ALIASES,
    DEFAULT_STATE_PATH,
    FLEXIBLE_SCORE_NAME_KEYWORDS,
    IntegratedFusionResult,
    MODALITY_DISCOVERY_KEYWORDS,
    SUPPORTED_SCORE_FILE_SUFFIXES,
    _default_local_manifest_path,
    _resolve_fusion_method,
    _resolve_output_destination,
    _run_fusion_predictions,
    _write_dataframe_destination,
    _write_json_destination,
    build_integration_manifest,
)
from src.loaders import CSV_MISSING_VALUES, load_inference_dataframe_from_dataframe
from src.utils import get_project_root, load_config, resolve_project_path

GENERIC_SCORE_KEYS = ("score", "probability", "prediction", "malicious_probability")
NUMERIC_VALUE_REGEX = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass
class ProcessedEmailEntry:
    """Directory-scan result for a single processed email folder."""

    email_id: str
    directory: str
    signature: str
    status: str
    reason: str | None
    scores: dict[str, float | None]
    source_files: dict[str, str | None]
    output_file: str | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_probability(value: object) -> float | None:
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if 0.0 <= numeric <= 1.0:
        return numeric
    return None


def _normalize_text(value: object) -> str:
    return str(value).strip().lower()


def _compute_directory_signature(email_dir: Path, ignored_filenames: set[str] | None = None) -> str:
    ignored = {name.lower() for name in (ignored_filenames or set())}
    files = [
        path
        for path in email_dir.rglob("*")
        if path.is_file() and path.name.lower() not in ignored
    ]
    latest_ns = max((path.stat().st_mtime_ns for path in files), default=email_dir.stat().st_mtime_ns)
    return f"{latest_ns}:{len(files)}"


def _iter_email_directories(processed_emails_root: Path) -> list[Path]:
    return sorted([path for path in processed_emails_root.iterdir() if path.is_dir()], key=lambda path: path.name)


def _score_candidate_path(path: Path, model_name: str) -> int:
    lower_path = str(path).lower()
    lower_name = path.name.lower()
    lower_stem = path.stem.lower()
    score = 0

    for hint in DEFAULT_DIRECTORY_SCORE_FILE_HINTS[model_name]:
        if hint in lower_path:
            score += 10

    if any(keyword in lower_path for keyword in MODALITY_DISCOVERY_KEYWORDS[model_name]):
        score += 4

    if any(keyword in lower_stem for keyword in FLEXIBLE_SCORE_NAME_KEYWORDS):
        score += 3

    if any(keyword in lower_name for keyword in ("output", "result", "prediction")):
        score += 2

    return score


def discover_score_file_candidates(
    email_dir: Path,
    model_name: str,
    ignored_filenames: set[str] | None = None,
) -> list[Path]:
    ignored = {name.lower() for name in (ignored_filenames or set())}
    candidates = [
        path
        for path in email_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_SCORE_FILE_SUFFIXES
        and path.name.lower() not in ignored
    ]
    ranked = sorted(
        candidates,
        key=lambda path: (_score_candidate_path(path, model_name), path.stat().st_mtime_ns),
        reverse=True,
    )
    return [path for path in ranked if _score_candidate_path(path, model_name) > 0]


def _extract_probability_from_json_payload(payload: object, model_name: str) -> float | None:
    aliases = {_normalize_text(alias) for alias in DEFAULT_SCORE_KEY_ALIASES[model_name]}
    modality_keywords = MODALITY_DISCOVERY_KEYWORDS[model_name]

    if isinstance(payload, dict):
        normalized_items = {str(key).strip().lower(): value for key, value in payload.items()}

        for key in aliases:
            if key in normalized_items:
                probability = _safe_probability(normalized_items[key])
                if probability is not None:
                    return probability

        declared_model = _normalize_text(
            normalized_items.get("model")
            or normalized_items.get("modality")
            or normalized_items.get("type")
            or ""
        )
        if declared_model and any(keyword in declared_model for keyword in modality_keywords):
            for key in GENERIC_SCORE_KEYS:
                if key in normalized_items:
                    probability = _safe_probability(normalized_items[key])
                    if probability is not None:
                        return probability

        for key, value in normalized_items.items():
            if any(keyword in key for keyword in modality_keywords) and any(token in key for token in FLEXIBLE_SCORE_NAME_KEYWORDS):
                probability = _safe_probability(value)
                if probability is not None:
                    return probability

        for value in normalized_items.values():
            if isinstance(value, (dict, list)):
                probability = _extract_probability_from_json_payload(value, model_name)
                if probability is not None:
                    return probability

        return None

    if isinstance(payload, list):
        for item in payload:
            probability = _extract_probability_from_json_payload(item, model_name)
            if probability is not None:
                return probability
        return None

    return None


def _infer_score_column(dataframe: pd.DataFrame, model_name: str) -> str | None:
    normalized_columns = [str(column).strip() for column in dataframe.columns]
    aliases = [_normalize_text(alias) for alias in DEFAULT_SCORE_KEY_ALIASES[model_name]]
    lowered = {str(column).strip().lower(): str(column).strip() for column in normalized_columns}

    for alias in aliases:
        if alias in lowered:
            return lowered[alias]

    for lowered_name, original_name in lowered.items():
        if any(keyword in lowered_name for keyword in MODALITY_DISCOVERY_KEYWORDS[model_name]) and any(
            token in lowered_name for token in FLEXIBLE_SCORE_NAME_KEYWORDS
        ):
            return original_name

    for lowered_name, original_name in lowered.items():
        if any(token in lowered_name for token in GENERIC_SCORE_KEYS):
            return original_name

    numeric_columns = [
        column for column in normalized_columns if pd.to_numeric(dataframe[column], errors="coerce").notna().any()
    ]
    if len(numeric_columns) == 1:
        return numeric_columns[0]
    return None


def _extract_probability_from_csv(path: Path, model_name: str, email_id: str) -> float | None:
    dataframe = pd.read_csv(path, keep_default_na=True, na_values=CSV_MISSING_VALUES)
    dataframe.columns = [str(column).strip() for column in dataframe.columns]

    email_id_column = next((column for column in dataframe.columns if _normalize_text(column) in DEFAULT_EMAIL_ID_ALIASES), None)
    if email_id_column is not None:
        filtered = dataframe[dataframe[email_id_column].astype("string").str.strip() == email_id]
        if filtered.empty:
            filtered = dataframe
    else:
        filtered = dataframe

    score_column = _infer_score_column(filtered, model_name)
    if score_column is None:
        return None

    numeric_values = pd.to_numeric(filtered[score_column], errors="coerce").dropna()
    numeric_values = numeric_values[(numeric_values >= 0.0) & (numeric_values <= 1.0)]
    if numeric_values.empty:
        return None

    if model_name == "malware":
        return float(numeric_values.max())
    return float(numeric_values.iloc[0])


def _extract_probability_from_text(text: str) -> float | None:
    for match in NUMERIC_VALUE_REGEX.findall(text):
        probability = _safe_probability(match)
        if probability is not None:
            return probability
    return None


def read_local_score_file(path: Path, model_name: str, email_id: str) -> float | None:
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return _extract_probability_from_json_payload(payload, model_name)
    if suffix == ".csv":
        return _extract_probability_from_csv(path, model_name, email_id=email_id)
    if suffix == ".txt":
        return _extract_probability_from_text(path.read_text(encoding="utf-8"))
    return None


def _discover_scores_for_email(
    email_dir: Path,
    email_id: str,
    ignored_filenames: set[str] | None = None,
) -> tuple[dict[str, float | None], dict[str, str | None], dict[str, str | None]]:
    scores: dict[str, float | None] = {BRANCH_SCORE_COLUMN_BY_MODEL[model]: None for model in BRANCH_MODELS}
    source_files: dict[str, str | None] = {model: None for model in BRANCH_MODELS}
    parse_errors: dict[str, str | None] = {model: None for model in BRANCH_MODELS}

    for model_name in BRANCH_MODELS:
        candidates = discover_score_file_candidates(email_dir, model_name, ignored_filenames=ignored_filenames)
        for candidate in candidates:
            try:
                probability = read_local_score_file(candidate, model_name, email_id=email_id)
            except Exception as exc:  # pragma: no cover - error recorded for diagnostics
                parse_errors[model_name] = str(exc)
                continue

            if probability is not None:
                scores[BRANCH_SCORE_COLUMN_BY_MODEL[model_name]] = probability
                source_files[model_name] = str(candidate)
                parse_errors[model_name] = None
                break

    return scores, source_files, parse_errors


def load_processed_emails_state(state_path: str | Path | None = None) -> dict[str, Any]:
    resolved_path = resolve_project_path(state_path or DEFAULT_STATE_PATH)
    if not resolved_path.exists():
        return {"processed_emails": {}}
    return json.loads(resolved_path.read_text(encoding="utf-8"))


def _build_processed_emails_dataframe(entries: list[ProcessedEmailEntry]) -> pd.DataFrame:
    rows = []
    for entry in entries:
        if entry.status != "ready":
            continue
        row = {"email_id": entry.email_id}
        row.update(entry.scores)
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=INFERENCE_INPUT_COLUMNS)
    return load_inference_dataframe_from_dataframe(pd.DataFrame(rows))


def scan_processed_emails_directory(
    processed_emails_root: str | Path,
    required_models: tuple[str, ...] = DEFAULT_DIRECTORY_REQUIRED_MODELS,
    incremental: bool = True,
    state: dict[str, Any] | None = None,
    ignored_filenames: set[str] | None = None,
) -> list[ProcessedEmailEntry]:
    root = resolve_project_path(processed_emails_root)
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"processed_emails root not found or not a directory: {root}")

    state_payload = state or {"processed_emails": {}}
    previous_entries = state_payload.get("processed_emails", {})
    results: list[ProcessedEmailEntry] = []

    for email_dir in _iter_email_directories(root):
        email_id = email_dir.name
        signature = _compute_directory_signature(email_dir, ignored_filenames=ignored_filenames)
        previous_entry = previous_entries.get(email_id, {})

        if incremental and previous_entry.get("signature") == signature and previous_entry.get("status") == "processed":
            results.append(
                ProcessedEmailEntry(
                    email_id=email_id,
                    directory=str(email_dir),
                    signature=signature,
                    status="unchanged",
                    reason="directory signature unchanged",
                    scores={
                        column: previous_entry.get("scores", {}).get(column)
                        for column in BRANCH_SCORE_COLUMN_BY_MODEL.values()
                    },
                    source_files={
                        model: previous_entry.get("source_files", {}).get(model)
                        for model in BRANCH_MODELS
                    },
                    output_file=previous_entry.get("output_file"),
                )
            )
            continue

        scores, source_files, parse_errors = _discover_scores_for_email(
            email_dir,
            email_id=email_id,
            ignored_filenames=ignored_filenames,
        )
        missing_required = [
            model_name for model_name in required_models if scores[BRANCH_SCORE_COLUMN_BY_MODEL[model_name]] is None
        ]

        if missing_required:
            results.append(
                ProcessedEmailEntry(
                    email_id=email_id,
                    directory=str(email_dir),
                    signature=signature,
                    status="skipped_missing_required",
                    reason=(
                        f"missing required scores for models: {missing_required}. "
                        f"Parse diagnostics: {parse_errors}"
                    ),
                    scores=scores,
                    source_files=source_files,
                )
            )
            continue

        if all(value is None for value in scores.values()):
            results.append(
                ProcessedEmailEntry(
                    email_id=email_id,
                    directory=str(email_dir),
                    signature=signature,
                    status="skipped_no_scores",
                    reason=f"no usable score files discovered. Parse diagnostics: {parse_errors}",
                    scores=scores,
                    source_files=source_files,
                )
            )
            continue

        results.append(
            ProcessedEmailEntry(
                email_id=email_id,
                directory=str(email_dir),
                signature=signature,
                status="ready",
                reason=None,
                scores=scores,
                source_files=source_files,
            )
        )

    return results


def _empty_predictions_dataframe() -> pd.DataFrame:
    return pd.DataFrame(columns=OUTPUT_COLUMNS)


def _default_directory_output_path(method: str) -> Path:
    return get_project_root() / "artifacts" / f"processed_emails_{method}_predictions.csv"


def _default_directory_manifest_path(method: str) -> Path:
    return get_project_root() / "artifacts" / f"processed_emails_{method}_manifest.json"


def _write_per_email_outputs(
    predictions: pd.DataFrame,
    entries: list[ProcessedEmailEntry],
    per_email_output_filename: str,
) -> dict[str, str]:
    output_paths: dict[str, str] = {}
    prediction_by_email = {str(row["email_id"]): row for row in predictions.to_dict(orient="records")}

    for entry in entries:
        if entry.status != "ready":
            continue
        prediction = prediction_by_email.get(entry.email_id)
        if prediction is None:
            continue
        output_path = Path(entry.directory) / per_email_output_filename
        payload = {
            **prediction,
            "email_id": entry.email_id,
            "source_files": entry.source_files,
            "generated_at": _utc_now_iso(),
        }
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        output_paths[entry.email_id] = str(output_path)
    return output_paths


def _update_state_payload(
    state_payload: dict[str, Any],
    entries: list[ProcessedEmailEntry],
    per_email_outputs: dict[str, str],
) -> dict[str, Any]:
    processed_emails = state_payload.setdefault("processed_emails", {})
    timestamp = _utc_now_iso()

    for entry in entries:
        existing_entry = processed_emails.get(entry.email_id, {})
        processed_emails[entry.email_id] = {
            "directory": entry.directory,
            "signature": entry.signature,
            "status": "processed" if entry.status == "ready" else entry.status,
            "reason": entry.reason,
            "scores": entry.scores if entry.status != "unchanged" else existing_entry.get("scores", entry.scores),
            "source_files": (
                entry.source_files if entry.status != "unchanged" else existing_entry.get("source_files", entry.source_files)
            ),
            "output_file": per_email_outputs.get(entry.email_id) or existing_entry.get("output_file"),
            "updated_at": timestamp,
        }

    return state_payload


def run_processed_emails_fusion(
    *,
    processed_emails_root: str | Path,
    fusion_method: str | None = None,
    output_path: str | Path | None = None,
    assembled_input_output: str | Path | None = None,
    manifest_output: str | Path | None = None,
    state_path: str | Path | None = None,
    config_path: str | Path | None = None,
    model_artifact: str | Path | None = None,
    per_email_output_filename: str | None = None,
    incremental: bool = True,
) -> IntegratedFusionResult:
    """Run fusion directly from a local processed_emails directory tree."""

    config = load_config(config_path)
    method = _resolve_fusion_method(fusion_method, config)
    processed_emails_config = config.get("integration", {}).get("processed_emails", {})
    configured_required_models = tuple(processed_emails_config.get("required_models", DEFAULT_DIRECTORY_REQUIRED_MODELS))
    configured_state_path = state_path or processed_emails_config.get("state_path") or DEFAULT_STATE_PATH
    configured_incremental = bool(processed_emails_config.get("incremental", incremental)) if state_path is None else incremental
    configured_per_email_output_filename = str(
        per_email_output_filename
        or processed_emails_config.get("per_email_output_filename", DEFAULT_PER_EMAIL_OUTPUT_FILENAME)
    )

    state_payload = load_processed_emails_state(configured_state_path)
    ignored_filenames = {configured_per_email_output_filename, ".ds_store"}

    entries = scan_processed_emails_directory(
        processed_emails_root=processed_emails_root,
        required_models=configured_required_models,
        incremental=configured_incremental,
        state=state_payload,
        ignored_filenames=ignored_filenames,
    )
    ready_count = sum(1 for entry in entries if entry.status == "ready")
    unchanged_count = sum(1 for entry in entries if entry.status == "unchanged")
    skipped_count = sum(1 for entry in entries if entry.status.startswith("skipped_"))
    assembled_input = _build_processed_emails_dataframe(entries)

    if assembled_input.empty:
        predictions = _empty_predictions_dataframe()
    else:
        predictions = _run_fusion_predictions(
            assembled_input=assembled_input,
            fusion_method=method,
            config=config,
            model_artifact=model_artifact,
            s3_client=None,
        )

    resolved_output_destination = output_path or _default_directory_output_path(method)
    output_location = _write_dataframe_destination(
        predictions,
        resolved_output_destination,
        s3_client=None,
        validate_as_output=not str(resolved_output_destination).startswith("s3://"),
    )

    assembled_input_location: str | None = None
    if assembled_input_output is not None:
        assembled_input_location = _write_dataframe_destination(
            assembled_input,
            assembled_input_output,
            validate_as_output=False,
        )

    per_email_outputs = _write_per_email_outputs(
        predictions=predictions,
        entries=entries,
        per_email_output_filename=configured_per_email_output_filename,
    )

    directory_manifest = build_integration_manifest(
        assembled_input=assembled_input,
        predictions=predictions,
        fusion_method=method,
        join_type="directory_scan",
        sources={"processed_emails_root": str(resolve_project_path(processed_emails_root))},
        duplicate_strategies={"directory_mode": "per-email discovery"},
    )
    directory_manifest.update(
        {
            "input_mode": "processed_emails_directory",
            "processed_emails_root": str(resolve_project_path(processed_emails_root)),
            "incremental": bool(configured_incremental),
            "scanned_email_directories": len(entries),
            "ready_email_directories": ready_count,
            "unchanged_email_directories": unchanged_count,
            "skipped_email_directories": skipped_count,
            "required_models": list(configured_required_models),
            "no_new_data": ready_count == 0 and unchanged_count > 0,
            "entries": [asdict(entry) for entry in entries],
            "per_email_output_filename": configured_per_email_output_filename,
        }
    )

    resolved_manifest_output = manifest_output or _default_directory_manifest_path(method)
    manifest_location = _write_json_destination(directory_manifest, resolved_manifest_output)

    updated_state = _update_state_payload(state_payload, entries, per_email_outputs)
    resolved_state_path = resolve_project_path(configured_state_path)
    resolved_state_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_state_path.write_text(json.dumps(updated_state, indent=2, sort_keys=True), encoding="utf-8")

    return IntegratedFusionResult(
        assembled_input=assembled_input,
        predictions=predictions,
        manifest=directory_manifest,
        output_location=output_location,
        assembled_input_location=assembled_input_location,
        manifest_location=manifest_location,
        state_location=str(resolved_state_path),
    )