"""Tests for preprocessing and missing-value handling."""

from __future__ import annotations

import pandas as pd

from src.preprocess import annotate_model_availability, prepare_logistic_features


def test_annotate_model_availability_builds_models_used(sample_inference_df: pd.DataFrame) -> None:
    annotated = annotate_model_availability(sample_inference_df)

    assert annotated.loc[0, "models_used"] == "header|body|malware"
    assert annotated.loc[1, "models_used"] == "header|body"
    assert annotated.loc[1, "has_malware"] == 0


def test_prepare_logistic_features_imputes_missing_values(sample_inference_df: pd.DataFrame) -> None:
    annotated, features = prepare_logistic_features(sample_inference_df, imputation_value=0.50)

    assert annotated.loc[1, "models_present_count"] == 2
    assert features.loc[1, "p_malware_filled"] == 0.50
    assert features.loc[1, "has_malware"] == 0
