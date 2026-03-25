"""CSV loaders and writers for fusion-layer workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

from src.contracts import INFERENCE_INPUT_COLUMNS, OUTPUT_COLUMNS, TRAINING_INPUT_COLUMNS
from src.validators import (
    validate_contract_columns,
    validate_inference_dataframe,
    validate_output_dataframe,
    validate_training_dataframe,
)

CSV_MISSING_VALUES = ["", " ", "NA", "NaN", "nan", "None", "null"]


def _read_csv(path: str | Path, expected_columns: Sequence[str]) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    dataframe = pd.read_csv(
        csv_path,
        dtype={"email_id": "string"},
        keep_default_na=True,
        na_values=CSV_MISSING_VALUES,
    )
    dataframe.columns = [str(column).strip() for column in dataframe.columns]
    validate_contract_columns(dataframe, expected_columns, f"CSV file {csv_path.name}")
    return dataframe.loc[:, list(expected_columns)].copy()


def _coerce_numeric_columns(df: pd.DataFrame, numeric_columns: Iterable[str]) -> pd.DataFrame:
    coerced = df.copy()
    for column in numeric_columns:
        coerced[column] = pd.to_numeric(coerced[column], errors="coerce")
    coerced["email_id"] = coerced["email_id"].astype("string").str.strip()
    return coerced


def load_training_dataframe(path: str | Path) -> pd.DataFrame:
    """Load and validate a labeled fusion-training CSV."""

    dataframe = _read_csv(path, TRAINING_INPUT_COLUMNS)
    dataframe = _coerce_numeric_columns(dataframe, ["p_header", "p_body", "p_malware", "true_label"])
    validated = validate_training_dataframe(dataframe)
    validated["true_label"] = validated["true_label"].astype(int)
    return validated


def load_inference_dataframe(path: str | Path) -> pd.DataFrame:
    """Load and validate an unlabeled fusion-inference CSV."""

    dataframe = _read_csv(path, INFERENCE_INPUT_COLUMNS)
    return load_inference_dataframe_from_dataframe(dataframe)


def load_inference_dataframe_from_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Validate an in-memory inference dataframe against the fusion contract.

    This helper supports cloud/runtime workflows (for example Lambda + S3)
    where inference rows may already be loaded into a dataframe.
    """

    normalized = dataframe.copy()
    normalized.columns = [str(column).strip() for column in normalized.columns]
    validate_contract_columns(normalized, INFERENCE_INPUT_COLUMNS, "inference dataframe")
    normalized = _coerce_numeric_columns(normalized, ["p_header", "p_body", "p_malware"])
    return validate_inference_dataframe(normalized)


def write_output_dataframe(dataframe: pd.DataFrame, path: str | Path) -> Path:
    """Validate and write the fusion output CSV."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    validated = validate_output_dataframe(dataframe.loc[:, list(OUTPUT_COLUMNS)].copy())
    validated.to_csv(output_path, index=False)
    return output_path
