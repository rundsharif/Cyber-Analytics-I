"""Dataframe-level validators built on top of the row-level contracts."""

from __future__ import annotations

from typing import Iterable, Sequence

import pandas as pd

from src.contracts import (
    FusionInferenceRecord,
    FusionOutputRecord,
    FusionTrainingRecord,
    INFERENCE_INPUT_COLUMNS,
    MODEL_PROBABILITY_COLUMNS,
    OUTPUT_COLUMNS,
    TRAINING_INPUT_COLUMNS,
)


def validate_contract_columns(
    df: pd.DataFrame,
    expected_columns: Sequence[str],
    dataset_name: str,
) -> None:
    """Ensure the dataframe exactly matches the expected contract columns."""

    missing = [column for column in expected_columns if column not in df.columns]
    extras = [column for column in df.columns if column not in expected_columns]
    if missing or extras:
        messages = []
        if missing:
            messages.append(f"missing columns: {missing}")
        if extras:
            messages.append(f"unexpected columns: {extras}")
        raise ValueError(f"{dataset_name} contract mismatch: {'; '.join(messages)}")


def validate_email_ids(df: pd.DataFrame) -> None:
    """Validate email identifiers."""

    if df["email_id"].isna().any():
        raise ValueError("email_id contains missing values.")
    empty_ids = df["email_id"].astype("string").str.strip().eq("")
    if empty_ids.any():
        raise ValueError("email_id contains empty strings.")
    duplicates = df[df["email_id"].duplicated()]["email_id"].tolist()
    if duplicates:
        raise ValueError(f"Duplicate email_id values found: {duplicates}")


def validate_probability_columns(
    df: pd.DataFrame,
    probability_columns: Iterable[str] = MODEL_PROBABILITY_COLUMNS,
) -> None:
    """Ensure probability columns are numeric and within [0.0, 1.0] when present."""

    for column in probability_columns:
        non_null_values = df[column].dropna()
        invalid_mask = (non_null_values < 0.0) | (non_null_values > 1.0)
        if invalid_mask.any():
            bad_values = non_null_values[invalid_mask].tolist()
            raise ValueError(
                f"Column {column!r} contains probabilities outside [0.0, 1.0]: {bad_values}"
            )


def validate_at_least_one_modality(df: pd.DataFrame) -> None:
    """Require at least one model score per row."""

    no_modality_mask = df[list(MODEL_PROBABILITY_COLUMNS)].isna().all(axis=1)
    if no_modality_mask.any():
        invalid_ids = df.loc[no_modality_mask, "email_id"].tolist()
        raise ValueError(
            "Each row must contain at least one model probability. "
            f"Rows failing validation: {invalid_ids}"
        )


def validate_binary_labels(df: pd.DataFrame, label_column: str = "true_label") -> None:
    """Ensure training labels are binary."""

    if df[label_column].isna().any():
        raise ValueError(f"{label_column} contains missing values.")
    invalid_mask = ~df[label_column].isin([0, 1])
    if invalid_mask.any():
        invalid_values = df.loc[invalid_mask, label_column].tolist()
        raise ValueError(f"{label_column} must only contain 0 or 1. Found: {invalid_values}")


def _validate_rows_against_contract(df: pd.DataFrame, contract_type: type) -> None:
    for row in df.to_dict(orient="records"):
        contract_type.from_mapping(row)


def validate_training_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Validate a training dataframe against the training input contract."""

    validate_contract_columns(df, TRAINING_INPUT_COLUMNS, "training input")
    validate_email_ids(df)
    validate_probability_columns(df)
    validate_at_least_one_modality(df)
    validate_binary_labels(df)
    _validate_rows_against_contract(df, FusionTrainingRecord)
    return df.loc[:, list(TRAINING_INPUT_COLUMNS)]


def validate_inference_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Validate an inference dataframe against the inference input contract."""

    validate_contract_columns(df, INFERENCE_INPUT_COLUMNS, "inference input")
    validate_email_ids(df)
    validate_probability_columns(df)
    validate_at_least_one_modality(df)
    _validate_rows_against_contract(df, FusionInferenceRecord)
    return df.loc[:, list(INFERENCE_INPUT_COLUMNS)]


def validate_output_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Validate a fusion output dataframe against the output contract."""

    validate_contract_columns(df, OUTPUT_COLUMNS, "fusion output")
    validate_email_ids(df)
    _validate_rows_against_contract(df, FusionOutputRecord)
    return df.loc[:, list(OUTPUT_COLUMNS)]
