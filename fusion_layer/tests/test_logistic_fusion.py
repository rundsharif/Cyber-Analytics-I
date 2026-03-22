"""Tests for logistic regression stacking."""

from __future__ import annotations

import pandas as pd
import pytest

from src.contracts import OUTPUT_COLUMNS
from src.logistic_fusion import LogisticFusionModel


def test_logistic_fusion_fit_predict_save_and_load(
    sample_training_df: pd.DataFrame,
    sample_inference_df: pd.DataFrame,
    tmp_path,
) -> None:
    model = LogisticFusionModel(imputation_value=0.50, threat_threshold=0.50)
    model.fit(sample_training_df)

    predictions_before = model.predict(sample_inference_df)
    artifact_path = tmp_path / "logistic_fusion_model.joblib"
    model.save(artifact_path)

    loaded_model = LogisticFusionModel.load(artifact_path)
    predictions_after = loaded_model.predict(sample_inference_df)

    assert artifact_path.exists()
    assert list(predictions_before.columns) == list(OUTPUT_COLUMNS)
    assert predictions_before["final_score"].tolist() == pytest.approx(
        predictions_after["final_score"].tolist()
    )
    assert set(predictions_after["fusion_method"]) == {"logistic_regression_stacking"}


def test_logistic_fusion_metadata_contains_coefficients(sample_training_df: pd.DataFrame) -> None:
    model = LogisticFusionModel(imputation_value=0.50, threat_threshold=0.50)
    model.fit(sample_training_df)

    metadata = model.metadata(training_rows=len(sample_training_df))

    assert metadata["training_rows"] == len(sample_training_df)
    assert "coefficients" in metadata
    assert "p_header_filled" in metadata["coefficients"]
