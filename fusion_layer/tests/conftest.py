"""Shared pytest fixtures for fusion-layer tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def sample_training_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"email_id": "e1", "p_header": 0.90, "p_body": 0.84, "p_malware": 0.95, "true_label": 1},
            {"email_id": "e2", "p_header": 0.10, "p_body": 0.15, "p_malware": None, "true_label": 0},
            {"email_id": "e3", "p_header": 0.78, "p_body": 0.66, "p_malware": 0.22, "true_label": 1},
            {"email_id": "e4", "p_header": 0.12, "p_body": 0.20, "p_malware": None, "true_label": 0},
            {"email_id": "e5", "p_header": 0.85, "p_body": 0.75, "p_malware": 0.81, "true_label": 1},
            {"email_id": "e6", "p_header": 0.18, "p_body": 0.24, "p_malware": 0.10, "true_label": 0},
            {"email_id": "e7", "p_header": 0.67, "p_body": 0.59, "p_malware": None, "true_label": 1},
            {"email_id": "e8", "p_header": 0.08, "p_body": 0.11, "p_malware": 0.05, "true_label": 0},
        ]
    )


@pytest.fixture
def sample_inference_df(sample_training_df: pd.DataFrame) -> pd.DataFrame:
    return sample_training_df.drop(columns=["true_label"]).copy()
