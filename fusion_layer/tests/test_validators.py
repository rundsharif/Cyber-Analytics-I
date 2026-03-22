"""Tests for dataframe-level validation."""

from __future__ import annotations

import pandas as pd
import pytest

from src.validators import validate_inference_dataframe, validate_training_dataframe


def test_training_validator_rejects_duplicate_email_ids(sample_training_df: pd.DataFrame) -> None:
    invalid_df = sample_training_df.copy()
    invalid_df.loc[1, "email_id"] = invalid_df.loc[0, "email_id"]

    with pytest.raises(ValueError, match="Duplicate email_id"):
        validate_training_dataframe(invalid_df)


def test_inference_validator_rejects_rows_with_no_modalities(sample_inference_df: pd.DataFrame) -> None:
    invalid_df = sample_inference_df.copy()
    invalid_df.loc[0, ["p_header", "p_body", "p_malware"]] = [None, None, None]

    with pytest.raises(ValueError, match="at least one model probability"):
        validate_inference_dataframe(invalid_df)
