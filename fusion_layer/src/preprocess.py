"""Preprocessing helpers for explicit missing-modality handling."""

from __future__ import annotations

import pandas as pd

from src.contracts import MODEL_PROBABILITY_COLUMNS

MODEL_ALIAS_BY_COLUMN = {
    "p_header": "header",
    "p_body": "body",
    "p_malware": "malware",
}

PRESENCE_COLUMNS = ("has_header", "has_body", "has_malware")
FILLED_PROBABILITY_COLUMNS = ("p_header_filled", "p_body_filled", "p_malware_filled")
LOGISTIC_FEATURE_COLUMNS = (
    *FILLED_PROBABILITY_COLUMNS,
    *PRESENCE_COLUMNS,
    "models_present_count",
)


def _format_models_used(row: pd.Series) -> str:
    present_models = [
        alias
        for probability_column, alias in MODEL_ALIAS_BY_COLUMN.items()
        if pd.notna(row[probability_column])
    ]
    return "|".join(present_models)


def annotate_model_availability(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Add explicit presence flags and model-usage metadata.

    This is the central place where missing-modality handling becomes explicit.
    """

    annotated = dataframe.copy()
    for probability_column, alias in MODEL_ALIAS_BY_COLUMN.items():
        annotated[f"has_{alias}"] = annotated[probability_column].notna().astype(int)
    annotated["models_present_count"] = annotated[list(PRESENCE_COLUMNS)].sum(axis=1)
    annotated["models_used"] = annotated.apply(_format_models_used, axis=1)
    return annotated


def prepare_logistic_features(
    dataframe: pd.DataFrame,
    imputation_value: float = 0.50,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Prepare a feature matrix for logistic regression stacking.

    Missing probabilities are filled with a configurable neutral value, while
    presence flags preserve the information about which modalities were actually
    present.
    """

    annotated = annotate_model_availability(dataframe)
    for source_column, filled_column in zip(MODEL_PROBABILITY_COLUMNS, FILLED_PROBABILITY_COLUMNS):
        annotated[filled_column] = annotated[source_column].fillna(imputation_value).astype(float)
    feature_frame = annotated.loc[:, list(LOGISTIC_FEATURE_COLUMNS)].astype(float)
    return annotated, feature_frame
