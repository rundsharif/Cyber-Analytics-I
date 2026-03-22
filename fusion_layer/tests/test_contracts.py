"""Tests for row-level input/output contracts."""

from __future__ import annotations

import pytest

from src.contracts import FusionInferenceRecord, FusionOutputRecord, FusionTrainingRecord


def test_training_record_accepts_missing_malware_probability() -> None:
    record = FusionTrainingRecord(
        email_id="email-1",
        p_header=0.81,
        p_body=0.67,
        p_malware=None,
        true_label=1,
    )

    assert record.email_id == "email-1"
    assert record.p_malware is None
    assert record.true_label == 1


def test_inference_record_rejects_all_missing_modalities() -> None:
    with pytest.raises(ValueError, match="At least one model probability"):
        FusionInferenceRecord(
            email_id="email-2",
            p_header=None,
            p_body=None,
            p_malware=None,
        )


def test_training_record_rejects_invalid_probability() -> None:
    with pytest.raises(ValueError, match="p_header"):
        FusionTrainingRecord(
            email_id="email-3",
            p_header=1.20,
            p_body=0.20,
            p_malware=None,
            true_label=0,
        )


def test_output_record_accepts_expected_values() -> None:
    output = FusionOutputRecord(
        email_id="email-4",
        final_score=0.74,
        final_label=1,
        risk_level="high / malicious",
        models_used="header|body|malware",
        fusion_method="logistic_regression_stacking",
    )

    assert output.final_score == 0.74
    assert output.final_label == 1
